"""Offline wheelgap target checks with independent positive and mutant oracles."""

import json
import re
import shutil
import subprocess
import tomllib
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "sortedcontainers"
VERSION = "2.4.0"
TARGETS = ("linux-x86_64", "linux-aarch64", "musl-aarch64")


def _source_block(lock: str) -> str:
    blocks = re.split(r"(?=^\[\[package\]\]$)", lock, flags=re.M)
    selected = [
        block for block in blocks if re.search(r'^name = "sortedcontainers"$', block, flags=re.M)
    ]
    assert len(selected) == 1, "locked fixture identity drift"
    return selected[0]


def _check(path: Path) -> tuple[int, dict[str, object]]:
    executable = shutil.which("wheelgap")
    assert executable is not None, "wheelgap must be in the isolated group"
    result = subprocess.run(
        [
            executable,
            str(path),
            "-p",
            "3.14",
            "-t",
            ",".join(TARGETS),
            "--offline",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in {0, 1}, result.stderr
    return result.returncode, json.loads(result.stdout)


def _make_lock(tmp_path: Path, variant: str) -> Path:
    source = (ROOT / "uv.lock").read_text()
    original = _source_block(source)
    parsed = tomllib.loads(original)
    assert parsed["package"][0]["name"] == PACKAGE
    assert parsed["package"][0]["version"] == VERSION
    assert parsed["package"][0]["sdist"]
    assert parsed["package"][0]["wheels"]
    if variant == "baseline":
        replacement = original
    else:
        replacement, count = re.subn(
            r"^wheels = \[\n.*?^\]\n",
            "wheels = []\n",
            original,
            flags=re.M | re.S,
        )
        assert count == 1
        if variant == "missing":
            replacement, count = re.subn(
                r"^sdist = \{[^\n]+\}\n",
                "",
                replacement,
                flags=re.M,
            )
            assert count == 1
        else:
            assert variant == "source_only"
    target_dir = tmp_path / variant
    target_dir.mkdir()
    target = target_dir / "uv.lock"
    target.write_text(source.replace(original, replacement, 1))
    assert len(tomllib.loads(target.read_text())["package"]) == len(
        tomllib.loads(source)["package"]
    )
    return target


def _result_for_package(result: dict[str, object]) -> dict[str, object]:
    packages = result.get("packages")
    assert isinstance(packages, list)
    selected = [
        package
        for package in packages
        if isinstance(package, dict) and package.get("name") == PACKAGE
    ]
    assert len(selected) == 1
    return selected[0]


def test_pinned_tool_version_and_offline_clean_lock(tmp_path: Path) -> None:
    assert version("wheelgap") == "0.13.0"
    exit_code, result = _check(_make_lock(tmp_path, "baseline"))
    assert exit_code == 0
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["with_gaps"] == 0
    package = _result_for_package(result)
    results = package["results"]
    assert isinstance(results, dict)
    assert all(results[target] == "wheel" for target in TARGETS)


def test_wheel_removed_reports_source_and_fails(tmp_path: Path) -> None:
    exit_code, result = _check(_make_lock(tmp_path, "source_only"))
    assert exit_code == 1
    package = _result_for_package(result)
    results = package["results"]
    assert isinstance(results, dict)
    assert all(results[target] == "source" for target in TARGETS)


def test_all_artifacts_removed_reports_missing_and_fails(tmp_path: Path) -> None:
    exit_code, result = _check(_make_lock(tmp_path, "missing"))
    assert exit_code == 1
    package = _result_for_package(result)
    results = package["results"]
    assert isinstance(results, dict)
    assert all(results[target] == "missing" for target in TARGETS)
