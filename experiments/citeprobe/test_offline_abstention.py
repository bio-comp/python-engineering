"""Citeprobe offline abstention controls; not proof of real-source verification."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "reference",
    [
        "doi:10.1038/nphys1170",
        "doi:10.9999/abc123-fabricated-lab",
        "Vaswani et al. (2017). Attention Is All You Need. arXiv:1706.03762",
    ],
)
def test_empty_index_does_not_announce_fabrication(reference: str, tmp_path: Path) -> None:
    binary = shutil.which("citeprobe")
    assert binary is not None, "Pinned citeprobe experimental dependency is required"
    cache = tmp_path / "deliberately-empty-cache"
    result = subprocess.run(
        [
            binary,
            reference,
            "--sources",
            "crossref",
            "--offline",
            "--cache-dir",
            str(cache),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 3, result.stderr
    report = json.loads(result.stdout)
    assert report["verdict"] == "inconclusive"
    assert report["candidates"] == []
    assert report["assessments"] == []
    for source in report["source_runs"]:
        assert source["status"] == "skipped"
    assert not any(finding.get("severity") == "error" for finding in report.get("findings", []))


def test_invalid_source_input_is_not_treated_as_verified(tmp_path: Path) -> None:
    binary = shutil.which("citeprobe")
    assert binary is not None
    output = subprocess.run(
        [
            binary,
            "doi:10.9999/abc123-fabricated-lab",
            "--sources",
            "crossref",
            "--offline",
            "--cache-dir",
            str(tmp_path / "no-provider-data"),
            "--policy",
            "strict",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert output.returncode == 3, output.stderr
    assert json.loads(output.stdout)["verdict"] == "inconclusive"


def test_fail_on_never_does_not_bypass_missing_evidence(tmp_path: Path) -> None:
    binary = shutil.which("citeprobe")
    assert binary is not None
    result = subprocess.run(
        [
            binary,
            "doi:10.1038/nphys1170",
            "--sources",
            "crossref",
            "--offline",
            "--fail-on",
            "never",
            "--cache-dir",
            str(tmp_path / "empty-cache"),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 3, result.stderr
    report = json.loads(result.stdout)
    assert report["verdict"] == "inconclusive"
    assert all(row["status"] == "skipped" for row in report["source_runs"])
