"""Reproducible labeled Ruff/mypy delta without changing production config."""

import hashlib
import json
import re
import shutil
import subprocess
import tomllib
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "experiments" / "quality_config"
BASE = FIXTURE / "base.pyproject.toml"
CANDIDATE = FIXTURE / "candidate.pyproject.toml"


def _copy_source(tmp_path: Path, name: str) -> Path:
    target = tmp_path / "source.py"
    target.write_bytes((FIXTURE / "fixtures" / name).read_bytes())
    return target


def _ruff(config: Path, source: Path) -> tuple[int, set[str]]:
    ruff = shutil.which("ruff")
    assert ruff is not None, "Ruff is required; no silent skip"
    # Ruff interprets nonstandard TOML filenames as ruff.toml format.
    # Re-home each fragment under its canonical pyproject.toml name.
    with TemporaryDirectory() as directory:
        project_config = Path(directory) / "pyproject.toml"
        project_config.write_bytes(config.read_bytes())
        result = subprocess.run(
            [
                ruff,
                "check",
                "--config",
                str(project_config),
                "--output-format",
                "json",
                str(source),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
    assert result.returncode in {0, 1}, result.stderr
    records = json.loads(result.stdout)
    return result.returncode, {record["code"] for record in records}


def _mypy(config: Path, source: Path) -> tuple[int, set[str]]:
    result = subprocess.run(
        ["mypy", "--config-file", str(config), "--no-incremental", str(source)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode in {0, 1}, result.stderr
    return result.returncode, set(re.findall(r"\[([a-z][\w-]+)\]", result.stdout))


def test_baseline_configuration_contract() -> None:
    """Protect the complete experimental baseline, not merely a subset."""
    assert tomllib.loads(BASE.read_text(encoding="utf-8")) == {
        "tool": {
            "ruff": {
                "target-version": "py314",
                "line-length": 100,
                "lint": {"select": ["E", "F", "I", "B", "UP", "RUF"]},
            },
            "mypy": {"python_version": "3.14", "strict": True},
        }
    }


def test_candidate_configuration_contract() -> None:
    """Protect every declared candidate selector, switch, and error code."""
    assert tomllib.loads(CANDIDATE.read_text(encoding="utf-8")) == {
        "tool": {
            "ruff": {
                "target-version": "py314",
                "line-length": 100,
                "lint": {
                    "select": [
                        "E",
                        "F",
                        "I",
                        "B",
                        "UP",
                        "RUF",
                        "S",
                        "T20",
                        "DTZ",
                        "C4",
                        "SIM",
                        "PIE",
                        "ASYNC",
                        "PT",
                        "TRY",
                        "LOG",
                    ]
                },
            },
            "mypy": {
                "python_version": "3.14",
                "strict": True,
                "warn_unreachable": True,
                "disallow_any_explicit": True,
                "enable_error_code": [
                    "possibly-undefined",
                    "explicit-override",
                    "exhaustive-match",
                    "redundant-expr",
                    "ignore-without-code",
                    "unused-awaitable",
                ],
            },
        }
    }


@pytest.mark.parametrize(
    ("relative_path", "expected_sha256"),
    [
        (
            "fixtures/known_bad.py.txt",
            "7b80ae919768d2f069ea7e9341c21294f53df84eb7e07a8d652e771813ef9d2d",
        ),
        (
            "fixtures/known_good.py.txt",
            "7a0beb65b16416964c06bde5be97a587fc96383742bbcfd13ab85cf1d6a2700a",
        ),
        (
            "base.pyproject.toml",
            "bc679fa9722f77df12864d267adad015872319ac97910542fdd85bdb7ae37148",
        ),
        (
            "candidate.pyproject.toml",
            "18a0f97ded9bdf5d2bf29f61f3dcfb206a92e15e0a945a092c053981e0cefd16",
        ),
    ],
)
def test_frozen_experiment_bytes(relative_path: str, expected_sha256: str) -> None:
    """Identify fixture/configuration bytes independently of diagnostic outputs."""
    actual_sha256 = hashlib.sha256((FIXTURE / relative_path).read_bytes()).hexdigest()
    assert actual_sha256 == expected_sha256, relative_path


def test_checker_versions_are_pinned() -> None:
    assert version("ruff") == "0.17.5"
    assert version("mypy") == "1.20.2"


def test_mypy_candidate_catches_four_new_seeded_failure_classes(tmp_path: Path) -> None:
    source = _copy_source(tmp_path, "known_bad.py.txt")
    base_exit, base = _mypy(BASE, source)
    candidate_exit, candidate = _mypy(CANDIDATE, source)
    assert base_exit == 0, base
    assert base == set()
    assert candidate_exit == 1
    assert candidate - base == {
        "possibly-undefined",
        "explicit-override",
        "exhaustive-match",
        "explicit-any",
    }


def test_ruff_candidate_catches_new_seeded_flags(tmp_path: Path) -> None:
    source = _copy_source(tmp_path, "known_bad.py.txt")
    base_exit, base = _ruff(BASE, source)
    candidate_exit, candidate = _ruff(CANDIDATE, source)
    assert base_exit == candidate_exit == 1
    assert base == {"I001", "B006"}
    assert candidate - base == {"T201", "S602", "S607", "DTZ005", "C416"}


@pytest.mark.parametrize("config", [BASE, CANDIDATE])
def test_known_good_survives_both_checkers(config: Path, tmp_path: Path) -> None:
    source = _copy_source(tmp_path, "known_good.py.txt")
    assert _ruff(config, source) == (0, set())
    assert _mypy(config, source) == (0, set())
