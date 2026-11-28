"""Explicit, root-confined local receipt checks; declared hashes are never attestation."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from pydantic import Field

from python_engineering.reporting.models import Contract, Run


class ReceiptStatus(StrEnum):
    VERIFIED_LOCAL = "VERIFIED LOCAL BYTES (NOT SCIENTIFIC ATTESTATION)"
    REPLAY_VERIFIED = "VERIFIED LOCAL REPLAY POPULATION (NOT SCIENTIFIC ATTESTATION)"
    MISMATCH = "HASH MISMATCH"
    UNSAFE = "UNSAFE PATH - NOT READ"
    UNAVAILABLE = "UNVERIFIED - LOCAL SOURCE UNAVAILABLE"
    EXTERNAL = "UNVERIFIED - EXTERNAL SOURCE NOT FETCHED"
    NOT_CHECKED = "UNVERIFIED - NO AUTHORIZED EVIDENCE ROOT"
    NO_DIGEST = "UNVERIFIED - NO DECLARED DIGEST"


class ReceiptCheck(Contract):
    evidence_id: str
    status: ReceiptStatus
    declared_sha256: str | None
    observed_sha256: str | None = None
    replay_problem: str | None = Field(default=None, exclude_if=lambda value: value is None)


def _local_check(
    root: Path,
    source: str,
    declared: str | None,
) -> tuple[ReceiptStatus, str | None]:
    url = urlsplit(source)
    path = Path(source)
    windows = PureWindowsPath(source)
    if (
        path.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or ".." in path.parts
        or url.scheme
        or not path.parts
    ):
        return ReceiptStatus.UNSAFE, None
    if declared is None:
        return ReceiptStatus.NO_DIGEST, None
    item = root
    for part in path.parts:
        item = item / part
        if item.is_symlink():
            return ReceiptStatus.UNSAFE, None
    if not item.resolve().is_relative_to(root):
        return ReceiptStatus.UNSAFE, None
    if not item.is_file():
        return ReceiptStatus.UNAVAILABLE, None
    digest = hashlib.sha256()
    with item.open("rb") as file:
        for block in iter(lambda: file.read(65536), b""):
            digest.update(block)
    observed = digest.hexdigest()
    return (
        ReceiptStatus.VERIFIED_LOCAL if observed == declared else ReceiptStatus.MISMATCH,
        observed,
    )


# E-017 v3 has a frozen, finite replay population. This is the SHA-256 of
# sorted stage-relative POSIX paths, each followed by a newline. Derived from
# the frozen corpus, configuration controls, update specifications and the
# required receipt/snapshot lifecycle, not from the report's supplied map.
# Keep historical v1/v2 inputs and unrelated reporting protocols unchanged.
_E017_V3_MEMBER_COUNT = 754
_E017_V3_POPULATION_SHA256 = "5f803b73b79e74f674f7b10e68ee136b173020ad928056e99b055a9f943b682c"


def _validate_e017_v3_population(run: Run) -> None:
    """Prevent omission or truncation of the replay manifest for the frozen protocol."""
    if run.experiment.experiment_id != "E-017" or not (
        run.experiment.protocol_revision == "Q1-local-r2-v3"
        or run.rubric_revision == "e017-q1-case-acceptance-v3"
        or run.environment.harness_version == "e017-q1-r2-v3"
    ):
        return

    manifests = [e for e in run.evidence if e.replay_manifest is not None]
    if len(manifests) != 1 or manifests[0].evidence_id != "replay-population-v1":
        raise ValueError("E-017 v3 requires its complete replay manifest")
    aggregate = manifests[0]
    manifest = aggregate.replay_manifest
    if manifest is None:  # Narrow the optional model field.
        raise ValueError("E-017 v3 requires its complete replay manifest")
    members = manifest.members
    # Each individual report reference must be bound to the same member digest.
    if any(
        e.source_sha256 is None or members.get(e.source) != e.source_sha256 for e in run.evidence
    ):
        raise ValueError("E-017 v3 report references differ from replay manifest")
    if any(
        gate.passed is not None and aggregate.evidence_id not in gate.evidence_ids
        for gate in run.gates
    ):
        raise ValueError("E-017 v3 measured gate lacks replay manifest reference")

    # Normalize the user-selected evidence directories by their run identities;
    # the report's location and directory names are not part of the corpus.
    anchor = PurePosixPath(aggregate.source)
    lookup = {
        PurePosixPath(e.source)
        for e in run.evidence
        if PurePosixPath(e.source).name == "run-identity.json" and e.source != aggregate.source
    }
    updates = {
        PurePosixPath(e.source)
        for e in run.evidence
        if PurePosixPath(e.source).name == "identity.json"
    }
    if anchor.name != "run-identity.json" or len(lookup) != 1 or len(updates) != 1:
        raise ValueError("E-017 v3 replay stage identities missing or ambiguous")
    roots = {
        "extract": anchor.parent,
        "lookup": next(iter(lookup)).parent,
        "updates": next(iter(updates)).parent,
    }
    normalized = set()
    for name in members:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != name:
            raise ValueError("E-017 v3 replay path must be canonical and relative")
        matches = [(stage, root) for stage, root in roots.items() if path.is_relative_to(root)]
        if len(matches) != 1 or path == matches[0][1]:
            raise ValueError("E-017 v3 replay path has no unique stage identity")
        stage, root = matches[0]
        normalized.add(f"{stage}/{path.relative_to(root).as_posix()}")
    population = hashlib.sha256(("\n".join(sorted(normalized)) + "\n").encode()).hexdigest()
    if len(members) != _E017_V3_MEMBER_COUNT or population != _E017_V3_POPULATION_SHA256:
        raise ValueError("E-017 v3 replay manifest differs from frozen required population")


def verify_receipts(run: Run, *, evidence_root: Path | None = None) -> tuple[ReceiptCheck, ...]:
    """Verify individual receipts and, when requested, every replay manifest member."""
    _validate_e017_v3_population(run)
    resolved_root = evidence_root.resolve(strict=True) if evidence_root is not None else None
    if resolved_root is not None and not resolved_root.is_dir():
        raise ValueError("evidence root must be an existing directory")
    checks = []
    for e in run.evidence:
        url = urlsplit(e.source)
        problem = None
        if url.scheme in ("https", "http"):
            status, observed = ReceiptStatus.EXTERNAL, None
        elif resolved_root is None:
            status, observed = ReceiptStatus.NOT_CHECKED, None
        else:
            status, observed = _local_check(resolved_root, e.source, e.source_sha256)
        if e.replay_manifest is not None and resolved_root is not None:
            # Never accept just the anchor. Check every member, including absent ones.
            failures: list[tuple[ReceiptStatus, str]] = []
            for name, declared in e.replay_manifest.members.items():
                member_status, _ = _local_check(resolved_root, name, declared)
                if member_status != ReceiptStatus.VERIFIED_LOCAL:
                    failures.append((member_status, name))
            if failures:
                status, name = next(
                    (
                        entry
                        for entry in failures
                        if entry[0] in (ReceiptStatus.MISMATCH, ReceiptStatus.UNSAFE)
                    ),
                    failures[0],
                )
                problem = (
                    f"{len(failures)} replay members unverified; first selected failure: {name}"
                )
            elif status == ReceiptStatus.VERIFIED_LOCAL:
                status = ReceiptStatus.REPLAY_VERIFIED
        checks.append(
            ReceiptCheck(
                evidence_id=e.evidence_id,
                status=status,
                declared_sha256=e.source_sha256,
                observed_sha256=observed,
                replay_problem=problem,
            )
        )
    return tuple(checks)


def assert_required_replay(run: Run, checks: tuple[ReceiptCheck, ...]) -> None:
    """Opt-in replay completeness is a hard gate, even without an evidence root."""
    _validate_e017_v3_population(run)
    by_id = {check.evidence_id: check for check in checks}
    for evidence in run.evidence:
        if evidence.replay_manifest is None:
            continue
        check = by_id.get(evidence.evidence_id)
        if check is None or check.status != ReceiptStatus.REPLAY_VERIFIED:
            reason = (
                "missing verification"
                if check is None
                else (check.replay_problem or check.status.value)
            )
            raise ValueError(f"required replay evidence not verified: {reason}")


def assert_no_local_failures(checks: tuple[ReceiptCheck, ...]) -> None:
    """An explicit verification request must fail closed on mismatch/unsafe path."""
    failures = [
        f"{check.evidence_id}: {check.status.value}"
        for check in checks
        if check.status in (ReceiptStatus.MISMATCH, ReceiptStatus.UNSAFE)
    ]
    if failures:
        raise ValueError("local receipt integrity verification failed: " + "; ".join(failures))
