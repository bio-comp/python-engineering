"""E-005: replayable offline Pydantic runtime and type-checker measurements.

Runtime truth is established only by an actual pydantic.ValidationError.
All unexpected subprocess failures, checker output corruption, or misplaced
diagnostics fail closed; a low diagnostic count is not evidence of success.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from importlib.metadata import version
from pathlib import Path
from time import perf_counter_ns
from typing import Literal

from pydantic import BaseModel, ConfigDict

from experiments.e005.cases import CASES, Case

Severity = Literal["error", "warning", "information"]

# This wrapper reports a structured result exclusively for successful source
# execution or for an actual Pydantic validation exception. Any other exception
# is allowed to escape and must fail the parent experiment.
_RUNTIME_RUNNER = """
import json
import runpy
import sys
from pydantic import ValidationError

try:
    runpy.run_path(sys.argv[1], run_name="__main__")
except ValidationError as exc:
    print(json.dumps({"status": "pydantic-validation", "error_types":
                      [item["type"] for item in exc.errors(include_input=False)]}))
else:
    print(json.dumps({"status": "accepted", "error_types": []}))
"""


class Diagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    severity: Severity
    rule: str
    path: str
    line: int
    column: int | None = None
    message: str


class ConfigReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str
    contents: str


class EnvironmentProbe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: str
    command: tuple[str, ...]
    exit_code: int
    selected_site_packages: str
    stdout: str
    stderr: str
    stdout_sha256: str
    stderr_sha256: str


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: str
    exit_code: int
    elapsed_ms: float
    command: tuple[str, ...]
    cwd: str
    configs: tuple[ConfigReceipt, ...]
    environment_probe: EnvironmentProbe | None
    stdout: str
    stderr: str
    stdout_sha256: str
    stderr_sha256: str
    diagnostics: tuple[Diagnostic, ...]


class RuntimeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    expected_accepts: bool
    actual_accepts: bool
    runtime_failure: str | None = None
    validation_error_types: tuple[str, ...]
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    stdout_sha256: str
    stderr_sha256: str


class MatrixReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    python_version: str
    python_executable: str
    venv_path: str
    venv_name: str
    site_packages_path: str
    pydantic_version: str
    pydantic_settings_version: str
    fixture_sha256: str
    harness_sha256: str
    git_revision: str
    git_dirty: bool
    fixture_paths: dict[str, str]
    runtime_environment_sha256: str
    runtime_wrapper_sha256: str
    runtimes: tuple[RuntimeResult, ...]
    checkers: tuple[ToolResult, ...]
    checker_versions: dict[str, str]


class _PyreflyRawDiagnostic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    name: str
    severity: str
    description: str
    line: int
    column: int | None = None


class _PyreflyRawOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    errors: list[_PyreflyRawDiagnostic]


class _Position(BaseModel):
    model_config = ConfigDict(extra="ignore")

    line: int
    character: int


class _Range(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start: _Position


class _PyrightRawDiagnostic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file: str
    rule: str | None = None
    severity: str
    message: str
    range: _Range


class _PyrightSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    errorCount: int
    warningCount: int
    informationCount: int


class _PyrightRawOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    generalDiagnostics: list[_PyrightRawDiagnostic]
    summary: _PyrightSummary


class _RuntimePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["accepted", "pydantic-validation"]
    error_types: tuple[str, ...]


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _severity(value: str) -> Severity:
    if value == "error":
        return "error"
    if value == "warning":
        return "warning"
    if value in {"information", "info", "note"}:
        return "information"
    raise ValueError(f"Unknown checker diagnostic severity {value!r}")


def _known_case(path: str, files: dict[Path, str], cwd: Path) -> str:
    candidate = Path(path)
    absolute = candidate if candidate.is_absolute() else cwd / candidate
    identity = absolute.resolve(strict=False)
    if identity not in files:
        raise ValueError(f"Diagnostic not from an exact generated fixture: {path!r}")
    return files[identity]


def _parse_json(
    tool: str, output: str, files: dict[Path, str], cwd: Path
) -> tuple[Diagnostic, ...]:
    result: list[Diagnostic] = []
    if tool == "pyrefly":
        payload = _PyreflyRawOutput.model_validate_json(output)
        for item in payload.errors:
            result.append(
                Diagnostic(
                    case_id=_known_case(item.path, files, cwd),
                    rule=item.name,
                    severity=_severity(item.severity),
                    path=item.path,
                    line=item.line,
                    column=item.column,
                    message=item.description,
                )
            )
    else:
        payload_right = _PyrightRawOutput.model_validate_json(output)
        expected = payload_right.summary
        observed = {
            "error": sum(item.severity == "error" for item in payload_right.generalDiagnostics),
            "warning": sum(item.severity == "warning" for item in payload_right.generalDiagnostics),
            "information": sum(
                item.severity == "information" for item in payload_right.generalDiagnostics
            ),
        }
        if observed != {
            "error": expected.errorCount,
            "warning": expected.warningCount,
            "information": expected.informationCount,
        }:
            raise ValueError(f"{tool}: JSON summary does not match diagnostic records")
        for item_right in payload_right.generalDiagnostics:
            result.append(
                Diagnostic(
                    case_id=_known_case(item_right.file, files, cwd),
                    rule=item_right.rule or "unclassified",
                    severity=_severity(item_right.severity),
                    path=item_right.file,
                    line=item_right.range.start.line + 1,
                    column=item_right.range.start.character + 1,
                    message=item_right.message,
                )
            )
    return tuple(result)


# Both formats allow missing codes. Never drop an error merely because its
# original human-readable output lacks an optional rule suffix.
_MYPY_LINE = re.compile(
    r"^(?P<path>.+?\.py):(?P<line>\d+)(?::(?P<col>\d+))?: "
    r"(?P<level>error|warning|note): (?P<msg>.*?)(?:\s+\[(?P<rule>[\w-]+)\])?$"
)
_TY_LINE = re.compile(
    r"^(?P<path>.+?\.py):(?P<line>\d+):(?P<col>\d+): "
    r"(?P<level>error|warning)(?:\[(?P<rule>[\w-]+)\])?:? (?P<msg>.+)$"
)
_DIAGNOSTIC_HINT = re.compile(r"\b(?:error|warning|note)(?:\[[\w-]+\])?:", re.I)


def _parse_text(
    tool: str, output: str, files: dict[Path, str], cwd: Path
) -> tuple[Diagnostic, ...]:
    pattern = _TY_LINE if tool == "ty" else _MYPY_LINE
    issues: list[Diagnostic] = []
    for line in output.splitlines():
        matched = pattern.fullmatch(line)
        if matched is not None:
            if matched.group("rule") is None and re.search(r"\[[\w-]+$", matched.group("msg")):
                raise ValueError(f"Unrecognized {tool} diagnostic record: {line!r}")
            issues.append(
                Diagnostic(
                    case_id=_known_case(matched.group("path"), files, cwd),
                    severity=_severity(matched.group("level")),
                    rule=matched.group("rule") or "unclassified",
                    path=matched.group("path"),
                    line=int(matched.group("line")),
                    column=int(matched.group("col")) if matched.group("col") else None,
                    message=matched.group("msg"),
                )
            )
            continue
        # Do not confuse a summary, a source excerpt, or contextual text with a
        # diagnostic. But reject a diagnostic-shaped line that failed parsing.
        stripped = line.strip()
        if _DIAGNOSTIC_HINT.search(line) or stripped.startswith(
            ("error:", "Error:", "warning:", "Warning:")
        ):
            raise ValueError(f"Unrecognized {tool} diagnostic record: {line!r}")
    summary = re.search(
        r"(?m)^Found (\d+) diagnostics?$"
        if tool == "ty"
        else r"(?m)^Found (\d+) errors? in \d+ files?",
        output,
    )
    if summary is not None:
        observed = (
            len(issues) if tool == "ty" else sum(issue.severity == "error" for issue in issues)
        )
        if observed != int(summary.group(1)):
            raise ValueError(f"{tool}: output summary does not match parsed diagnostics")
    return tuple(issues)


def _exe(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise RuntimeError(f"Required checker executable unavailable: {name}")
    return found


def _receipt(path: Path, root: Path) -> ConfigReceipt:
    data = path.read_bytes()
    return ConfigReceipt(
        path=str(path.relative_to(root)), sha256=_sha(data), contents=data.decode()
    )


def _check_pyright_environment(
    tool: str, executable: str, cwd: Path, site_packages: Path
) -> EnvironmentProbe:
    command = [executable, "--project", str(cwd / "pyrightconfig.json"), "--verbose"]
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False, timeout=90)
    combined = proc.stdout + "\n" + proc.stderr
    if proc.returncode not in {0, 1}:
        raise RuntimeError(f"{tool}: environment probe failed with rc {proc.returncode}")
    if "venv .venv subdirectory not found" in combined.lower() or not any(
        line.strip() == str(site_packages) for line in combined.splitlines()
    ):
        raise RuntimeError(f"{tool}: intended site-packages absent from import resolution paths")
    return EnvironmentProbe(
        tool=tool,
        command=tuple(command),
        exit_code=proc.returncode,
        selected_site_packages=str(site_packages),
        stdout=proc.stdout,
        stderr=proc.stderr,
        stdout_sha256=_sha(proc.stdout.encode()),
        stderr_sha256=_sha(proc.stderr.encode()),
    )


def _invoke(
    tool: str,
    args: list[str],
    files: dict[Path, str],
    cwd: Path,
    configs: tuple[ConfigReceipt, ...],
    environment_probe: EnvironmentProbe | None = None,
) -> ToolResult:
    start = perf_counter_ns()
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False, timeout=90)
    elapsed = (perf_counter_ns() - start) / 1_000_000
    if proc.returncode not in {0, 1}:
        raise RuntimeError(
            f"{tool} failed ({proc.returncode}): stdout={proc.stdout[:500]!r},"
            f" stderr={proc.stderr[:500]!r}"
        )
    diagnostics = (
        _parse_json(tool, proc.stdout, files, cwd)
        if tool in {"pyrefly", "pyright", "basedpyright"}
        else _parse_text(tool, proc.stdout, files, cwd)
    )
    errors = [record for record in diagnostics if record.severity == "error"]
    if tool == "pyrefly":
        count_match = re.search(r"(?m)^\s*INFO (\d+) errors?$", proc.stderr)
        if count_match is not None and len(errors) != int(count_match.group(1)):
            raise RuntimeError("Pyrefly stderr error count disagrees with its JSON")
    elif _DIAGNOSTIC_HINT.search(proc.stderr):
        raise RuntimeError(f"{tool}: unexpected diagnostics on stderr")
    if proc.returncode == 1 and not errors:
        raise RuntimeError(f"{tool} exited 1 but yielded no parsable errors")
    if proc.returncode == 0 and errors:
        raise RuntimeError(f"{tool} exited 0 but reported {len(errors)} errors")
    return ToolResult(
        tool=tool,
        exit_code=proc.returncode,
        elapsed_ms=round(elapsed, 3),
        command=tuple(args),
        cwd=str(cwd),
        configs=configs,
        environment_probe=environment_probe,
        stdout=proc.stdout,
        stderr=proc.stderr,
        stdout_sha256=_sha(proc.stdout.encode()),
        stderr_sha256=_sha(proc.stderr.encode()),
        diagnostics=diagnostics,
    )


def _controlled_environment() -> dict[str, str]:
    # Intentionally exclude all ambient secrets/configuration, including ZONE,
    # PYTHONPATH, PYTHONOPTIMIZE and unrelated BaseSettings fields.
    result = {"PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    if sys.platform == "win32" and "SYSTEMROOT" in os.environ:
        result["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return result


def _run_case(case: Case, path: Path, cwd: Path) -> RuntimeResult:
    command = [sys.executable, "-I", "-B", "-c", _RUNTIME_RUNNER, str(path)]
    proc = subprocess.run(
        command,
        cwd=cwd,
        env=_controlled_environment(),
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{case.identifier}: unexpected non-Pydantic subprocess failure "
            f"({proc.returncode}): {proc.stderr[:500]!r}"
        )
    try:
        payload = _RuntimePayload.model_validate_json(proc.stdout)
    except ValueError as exc:
        raise RuntimeError(f"{case.identifier}: malformed runtime result") from exc
    if payload.status == "pydantic-validation" and not payload.error_types:
        raise RuntimeError(f"{case.identifier}: validation status missing error types")
    if payload.status == "accepted" and payload.error_types:
        raise RuntimeError(f"{case.identifier}: accepted status with validation errors")
    accepts = payload.status == "accepted"
    if accepts != case.runtime_accepts:
        raise RuntimeError(
            f"{case.identifier}: runtime acceptance {accepts} conflicts with "
            f"declared oracle {case.runtime_accepts}"
        )
    return RuntimeResult(
        case_id=case.identifier,
        expected_accepts=case.runtime_accepts,
        actual_accepts=accepts,
        runtime_failure=None if accepts else "pydantic-validation",
        validation_error_types=payload.error_types,
        command=tuple(command),
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        stdout_sha256=_sha(proc.stdout.encode()),
        stderr_sha256=_sha(proc.stderr.encode()),
    )


def _venv() -> tuple[Path, str, Path]:
    prefix = Path(sys.prefix).absolute()
    if sys.prefix == sys.base_prefix or not (prefix / "pyvenv.cfg").is_file():
        raise RuntimeError("E-005 requires an active, real Python virtual environment")
    if not Path(sys.executable).absolute().is_relative_to(prefix):
        raise RuntimeError("Python interpreter not inside expected virtual environment")
    site_packages = Path(sysconfig.get_paths()["purelib"]).absolute()
    if not site_packages.is_relative_to(prefix) or not site_packages.is_dir():
        raise RuntimeError("Installed dependencies do not resolve inside active virtual env")
    return prefix.parent, prefix.name, site_packages


def _git_revision() -> tuple[str, bool]:
    repo = Path(__file__).resolve().parents[2]
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    )
    return revision, dirty


def _harness_sha() -> str:
    root = Path(__file__).resolve().parents[2]
    parts = (
        "experiments/e005/matrix.py",
        "experiments/e005/cases.py",
        "experiments/e005/test_matrix.py",
    )
    serial = [(name, _sha((root / name).read_bytes())) for name in parts]
    return _sha(json.dumps(serial, separators=(",", ":")).encode())


def _corpus_sha() -> str:
    serialized = [
        {
            "identifier": case.identifier,
            "source": case.source,
            "expected_accepts": case.runtime_accepts,
            "rationale": case.rationale,
        }
        for case in CASES
    ]
    return _sha(json.dumps(serialized, sort_keys=True, separators=(",", ":")).encode())


def execute_matrix(root: Path) -> MatrixReport:
    """Qualify the frozen 16-case matrix; reject missing tools or corrupt evidence."""
    pinned = {
        "pyrefly": "1.4.1",
        "pyright": "1.1.414",
        "basedpyright": "1.40.2",
        "ty": "0.0.95",
        "mypy": "1.20.2",
        "pydantic": "2.14.1",
        "pydantic-settings": "2.16.3",
    }
    for package, required in pinned.items():
        if version(package) != required:
            raise RuntimeError(f"{package} is not pinned to expected {required}")
    venv_path, venv_name, site_packages = _venv()

    root = root.resolve()
    cases_dir = root / "cases"
    cases_dir.mkdir(parents=True, exist_ok=False)
    ids = [case.identifier for case in CASES]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate fixture IDs")
    filemap: dict[Path, str] = {}
    paths: list[str] = []
    runtimes: list[RuntimeResult] = []
    for case in CASES:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", case.identifier):
            raise RuntimeError(f"Invalid fixture ID: {case.identifier}")
        path = cases_dir / f"{case.identifier}.py"
        path.write_text(case.source, encoding="utf-8")
        filemap[path.resolve()] = case.identifier
        paths.append(str(path))
        runtimes.append(_run_case(case, path, root))

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
                "venvPath": str(venv_path),
                "venv": venv_name,
            },
            sort_keys=True,
        )
    )
    config_paths = {
        "mypy": (root / "mypy.ini",),
        "mypy-plugin": (root / "mypy-plugin.ini",),
        "pyrefly": (root / "pyrefly.toml",),
        "pyright": (root / "pyrightconfig.json",),
        "basedpyright": (root / "pyrightconfig.json",),
        "ty": (),
    }
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
            [
                _exe("basedpyright"),
                "--project",
                str(root / "pyrightconfig.json"),
                "--outputjson",
            ],
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
    result_list: list[ToolResult] = []
    for name, command in checks:
        probe = (
            _check_pyright_environment(name, command[0], root, site_packages)
            if name in {"pyright", "basedpyright"}
            else None
        )
        result_list.append(
            _invoke(
                name,
                command,
                filemap,
                root,
                tuple(_receipt(path, root) for path in config_paths[name]),
                environment_probe=probe,
            )
        )
    results = tuple(result_list)
    revision, dirty = _git_revision()
    return MatrixReport(
        python_version=".".join(str(part) for part in sys.version_info[:3]),
        python_executable=sys.executable,
        venv_path=str(venv_path),
        venv_name=venv_name,
        site_packages_path=str(site_packages),
        pydantic_version=version("pydantic"),
        pydantic_settings_version=version("pydantic-settings"),
        fixture_sha256=_corpus_sha(),
        harness_sha256=_harness_sha(),
        git_revision=revision,
        git_dirty=dirty,
        fixture_paths={case_id: str(path) for path, case_id in filemap.items()},
        runtime_environment_sha256=_sha(
            json.dumps(_controlled_environment(), sort_keys=True).encode()
        ),
        runtime_wrapper_sha256=_sha(_RUNTIME_RUNNER.encode()),
        runtimes=tuple(runtimes),
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
