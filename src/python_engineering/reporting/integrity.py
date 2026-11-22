"""Explicit, root-confined local receipt checks; declared hashes are never attestation."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit

from python_engineering.reporting.models import Contract, Run


class ReceiptStatus(StrEnum):
    VERIFIED_LOCAL = "VERIFIED LOCAL BYTES (NOT SCIENTIFIC ATTESTATION)"
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


def verify_receipts(run: Run, *, evidence_root: Path | None = None) -> tuple[ReceiptCheck, ...]:
    """Only read regular, non-symlinked files beneath an explicitly supplied root."""
    resolved_root = evidence_root.resolve(strict=True) if evidence_root is not None else None
    if resolved_root is not None and not resolved_root.is_dir():
        raise ValueError("evidence root must be an existing directory")
    checks = []
    for e in run.evidence:
        url = urlsplit(e.source)
        if url.scheme in ("https", "http"):
            status = ReceiptStatus.EXTERNAL
            observed = None
        elif resolved_root is None:
            status = ReceiptStatus.NOT_CHECKED
            observed = None
        else:
            path = Path(e.source)
            windows = PureWindowsPath(e.source)
            if (
                path.is_absolute()
                or windows.is_absolute()
                or windows.drive
                or ".." in path.parts
                or url.scheme
                or not path.parts
            ):
                status = ReceiptStatus.UNSAFE
                observed = None
            elif e.source_sha256 is None:
                status = ReceiptStatus.NO_DIGEST
                observed = None
            else:
                item = resolved_root
                bad_link = False
                for part in path.parts:
                    item = item / part
                    if item.is_symlink():
                        bad_link = True
                        break
                if bad_link or not item.resolve().is_relative_to(resolved_root):
                    status = ReceiptStatus.UNSAFE
                    observed = None
                elif not item.is_file():
                    status = ReceiptStatus.UNAVAILABLE
                    observed = None
                else:
                    # Hash actual bytes, not the caller's assertion.
                    digest = hashlib.sha256()
                    with item.open("rb") as file:
                        for block in iter(lambda: file.read(65536), b""):
                            digest.update(block)
                    observed = digest.hexdigest()
                    status = (
                        ReceiptStatus.VERIFIED_LOCAL
                        if observed == e.source_sha256
                        else ReceiptStatus.MISMATCH
                    )
        checks.append(
            ReceiptCheck(
                evidence_id=e.evidence_id,
                status=status,
                declared_sha256=e.source_sha256,
                observed_sha256=observed,
            )
        )
    return tuple(checks)


def assert_no_local_failures(checks: tuple[ReceiptCheck, ...]) -> None:
    """An explicit verification request must fail closed on mismatch/unsafe path."""
    failures = [
        f"{check.evidence_id}: {check.status.value}"
        for check in checks
        if check.status in (ReceiptStatus.MISMATCH, ReceiptStatus.UNSAFE)
    ]
    if failures:
        raise ValueError("local receipt integrity verification failed: " + "; ".join(failures))
