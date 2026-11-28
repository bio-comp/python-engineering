"""Explicit, root-confined local receipt checks; declared hashes are never attestation."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path, PureWindowsPath
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


def verify_receipts(run: Run, *, evidence_root: Path | None = None) -> tuple[ReceiptCheck, ...]:
    """Verify individual receipts and, when requested, every replay manifest member."""
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
