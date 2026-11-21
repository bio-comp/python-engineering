"""Exact SHA-256 fingerprints for immutable fixture and candidate bytes."""

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Fingerprint bytes without normalizing line endings or text."""
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            hasher.update(block)
    return hasher.hexdigest()
