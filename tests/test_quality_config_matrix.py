"""Reproducible labeled Ruff/mypy delta without changing production config."""

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


def test_configs_are_real_pyproject_fragments_and_keep_baseline() -> None:
    for path in (BASE, CANDIDATE):
        data = tomllib.loads(path.read_text())
        assert data["tool"]["mypy"]["strict"] is True
        assert data["tool"]["mypy"]["python_version"] == "3.14"
        assert set(("E", "F", "I", "B", "UP", "RUF")) <= set(data["tool"]["ruff"]["lint"]["select"])
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
