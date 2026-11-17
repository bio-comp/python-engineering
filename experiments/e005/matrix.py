"""Offline, source-backed Pydantic runtime and checker comparison (E-005).

A nonzero checker return is not automatically a true positive: diagnostics
are preserved by case for independent review of relevance and false positives.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from time import perf_counter_ns
from typing import Literal

from pydantic import BaseModel, ConfigDict

from experiments.e005.cases import CASES

Severity = Literal["error", "warning", "information"]


class Diagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    severity: Severity
    rule: str


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: str
    exit_code: int
    elapsed_ms: float
    diagnostics: tuple[Diagnostic, ...]


class RuntimeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    expected_accepts: bool
    actual_accepts: bool
    runtime_failure: str | None = None


class MatrixReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    python_version: str
    pydantic_version: str
    pydantic_settings_version: str
    fixture_sha256: str
    runtimes: tuple[RuntimeResult, ...]
    checkers: tuple[ToolResult, ...]
    checker_versions: dict[str, str]


class _PyreflyRawDiagnostic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    name: str
    severity: str


class _PyreflyRawOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    errors: list[_PyreflyRawDiagnostic]


class _PyrightRawDiagnostic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file: str
    rule: str | None = None
    severity: str


class _PyrightRawOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    generalDiagnostics: list[_PyrightRawDiagnostic]


def _severity(value: str) -> Severity:
    if value == "error":
        return "error"
    if value == "warning":
        return "warning"
    if value in {"information", "info", "note"}:
        return "information"
    raise ValueError(f"Unexpected severity: {value!r}")


def _known_case(path: str, ids: frozenset[str]) -> str:
    name = Path(path).stem
    if name not in ids:
        raise ValueError(f"Checker reported a diagnostic outside case corpus: {path}")
    return name


def _parse_json(tool: str, output: str, ids: frozenset[str]) -> tuple[Diagnostic, ...]:
    result: list[Diagnostic] = []
    if tool == "pyrefly":
        pyrefly_payload = _PyreflyRawOutput.model_validate_json(output)
        for pyrefly_issue in pyrefly_payload.errors:
            result.append(
                Diagnostic(
                    case_id=_known_case(pyrefly_issue.path, ids),
                    rule=pyrefly_issue.name,
                    severity=_severity(pyrefly_issue.severity),
                )
            )
    else:
        pyright_payload = _PyrightRawOutput.model_validate_json(output)
        for pyright_issue in pyright_payload.generalDiagnostics:
            result.append(
                Diagnostic(
                    case_id=_known_case(pyright_issue.file, ids),
                    rule=pyright_issue.rule or "unclassified",
                    severity=_severity(pyright_issue.severity),
                )
            )
    return tuple(result)


_MYPY_LINE = re.compile(
    r"^(?P<path>.+?\.py):\d+(?::\d+)?: (?P<level>error|warning|note): "
    r".*?\[(?P<rule>[\w-]+)\]$"
)
_TY_LINE = re.compile(r"^(?P<path>.+?\.py):\d+:\d+: (?P<level>error|warning)\[(?P<rule>[\w-]+)\]")


def _parse_text(tool: str, output: str, ids: frozenset[str]) -> tuple[Diagnostic, ...]:
    pattern = _TY_LINE if tool == "ty" else _MYPY_LINE
    issues: list[Diagnostic] = []
    for line in output.splitlines():
        match = pattern.match(line)
        if match is None:
            continue
        issues.append(
            Diagnostic(
                case_id=_known_case(match.group("path"), ids),
                severity=_severity(match.group("level")),
                rule=match.group("rule"),
            )
        )
    return tuple(issues)


def _exe(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise RuntimeError(f"Required pinned checker unavailable: {name}")
    return found


def _invoke(tool: str, args: list[str], ids: frozenset[str], cwd: Path) -> ToolResult:
    before = perf_counter_ns()
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False, timeout=90)
    elapsed = (perf_counter_ns() - before) / 1_000_000
    if result.returncode not in {0, 1}:
        raise RuntimeError(
            f"{tool} invocation failed ({result.returncode}): "
            f"{result.stderr[:300]} {result.stdout[:300]}"
        )
    if tool in {"pyrefly", "pyright", "basedpyright"}:
        diagnostics = _parse_json(tool, result.stdout, ids)
    else:
        diagnostics = _parse_text(tool, result.stdout, ids)
    if result.returncode == 1 and not diagnostics:
        raise RuntimeError(f"{tool} exited 1 but produced no parsable diagnostics")
    if result.returncode == 0 and any(issue.severity == "error" for issue in diagnostics):
        raise RuntimeError(f"{tool} reported error diagnostics yet exited 0")
    return ToolResult(
        tool=tool,
        exit_code=result.returncode,
        elapsed_ms=round(elapsed, 3),
        diagnostics=diagnostics,
    )


def execute_matrix(root: Path) -> MatrixReport:
    """Run a bounded synthetic comparison, without source mutation or network."""
    assert version("pyrefly") == "1.4.1"
    assert version("pyright") == "1.1.414"
    assert version("basedpyright") == "1.40.2"
    assert version("ty") == "0.0.95"
    assert version("mypy") == "1.20.2"
    assert version("pydantic") == "2.14.1"
    assert version("pydantic-settings") == "2.16.3"

    cases_dir = root / "cases"
    cases_dir.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256()
    ids = frozenset(case.identifier for case in CASES)
    assert len(ids) == len(CASES)
    runtime: list[RuntimeResult] = []
    paths: list[str] = []
    for case in CASES:
        digest.update(case.identifier.encode() + b"\x00" + case.source.encode())
        path = cases_dir / f"{case.identifier}.py"
        path.write_text(case.source, encoding="utf-8")
        paths.append(str(path))
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        if result.returncode != 0 and "ValidationError" not in result.stderr:
            raise RuntimeError(
                f"{case.identifier}: failure was not a Pydantic ValidationError: "
                f"{result.stderr[:300]}"
            )
        runtime.append(
            RuntimeResult(
                case_id=case.identifier,
                expected_accepts=case.runtime_accepts,
                actual_accepts=result.returncode == 0,
                runtime_failure=("pydantic-validation" if result.returncode != 0 else None),
            )
        )
    if any(entry.expected_accepts != entry.actual_accepts for entry in runtime):
        raise RuntimeError("Pinned Pydantic runtime disagrees with a declared oracle")

    (root / "mypy.ini").write_text("[mypy]\npython_version = 3.14\nstrict = True\n")
    (root / "mypy-plugin.ini").write_text(
        "[mypy]\npython_version = 3.14\nstrict = True\nplugins = pydantic.mypy\n"
    )
    (root / "pyrefly.toml").write_text('preset = "strict"\npython-version = "3.14"\n')
    (root / "pyrightconfig.json").write_text(
        json.dumps(
            {
                "typeCheckingMode": "strict",
                "pythonVersion": "3.14",
                "include": ["cases"],
                "venvPath": str(Path(sys.executable).resolve().parents[2]),
                "venv": ".venv",
            }
        )
    )
    checks = [
        (
            "mypy",
            [
                _exe("mypy"),
                "--config-file",
                str(root / "mypy.ini"),
                "--no-incremental",
                "--no-error-summary",
                "--show-error-codes",
                *paths,
            ],
        ),
        (
            "mypy-plugin",
            [
                _exe("mypy"),
                "--config-file",
                str(root / "mypy-plugin.ini"),
                "--no-incremental",
                "--no-error-summary",
                "--show-error-codes",
                *paths,
            ],
        ),
        (
            "pyrefly",
            [
                _exe("pyrefly"),
                "check",
                "--config",
                str(root / "pyrefly.toml"),
                "--python-interpreter-path",
                sys.executable,
                "--output-format",
                "json",
                *paths,
            ],
        ),
        (
            "pyright",
            [_exe("pyright"), "--project", str(root / "pyrightconfig.json"), "--outputjson"],
        ),
        (
            "basedpyright",
            [_exe("basedpyright"), "--project", str(root / "pyrightconfig.json"), "--outputjson"],
        ),
        (
            "ty",
            [
                _exe("ty"),
                "check",
                "--python",
                sys.executable,
                "--output-format",
                "concise",
                str(cases_dir),
            ],
        ),
    ]
    results = tuple(_invoke(name, cmd, ids, root) for name, cmd in checks)
    return MatrixReport(
        python_version=".".join(map(str, sys.version_info[:3])),
        pydantic_version=version("pydantic"),
        pydantic_settings_version=version("pydantic-settings"),
        fixture_sha256=digest.hexdigest(),
        runtimes=tuple(runtime),
        checkers=results,
        checker_versions={
            name: version(name) for name in ("mypy", "pyrefly", "pyright", "basedpyright", "ty")
        },
    )


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    with TemporaryDirectory(prefix="e005-matrix-") as directory:
        report = execute_matrix(Path(directory))
        print(report.model_dump_json(indent=2))
