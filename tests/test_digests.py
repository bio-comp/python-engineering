"""Verify raw-byte identity; no normalized-text shortcuts."""

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given
from hypothesis import strategies as st

from python_engineering.digests import sha256_file


@given(st.binary(max_size=2048))
def test_fixture_hash_matches_independent_hashlib(payload: bytes) -> None:
    with TemporaryDirectory() as directory:
        source = Path(directory) / "fixture"
        source.write_bytes(payload)
        assert sha256_file(source) == hashlib.sha256(payload).hexdigest()


def test_line_endings_have_distinct_digests(tmp_path: Path) -> None:
    file = tmp_path / "source.py"
    file.write_bytes(b"a\nb\n")
    original = sha256_file(file)
    file.write_bytes(b"a\r\nb\r\n")
    assert sha256_file(file) != original
