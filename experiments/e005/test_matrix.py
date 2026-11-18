"""E-005 independent runtime and checker comparator regression oracles."""

import hashlib
import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from experiments.e005.cases import CASES, Case
from experiments.e005.matrix import (
    _corpus_sha,
    _known_case,
    _parse_json,
    _parse_text,
    _run_case,
    _venv,
    execute_matrix,
)


def test_all_synthetic_contracts_and_checker_outputs(tmp_path: Path) -> None:
    report = execute_matrix(tmp_path)
    assert len(report.runtimes) == len(CASES) == 16
    assert all(row.actual_accepts == row.expected_accepts for row in report.runtimes)
    assert len(report.fixture_sha256) == 64
    assert len(report.harness_sha256) == 64
    assert len(report.runtime_wrapper_sha256) == 64
    assert len(report.git_revision) == 40
    assert report.venv_name == ".venv"
    assert Path(report.site_packages_path).is_relative_to(Path(report.venv_path) / report.venv_name)
    assert [row.tool for row in report.checkers] == [
        "mypy",
        "mypy-plugin",
        "pyrefly",
        "pyright",
        "basedpyright",
        "ty",
    ]
    for record in report.runtimes:
        assert record.exit_code == 0
        assert (
            record.validation_error_types
            if not record.actual_accepts
            else (not record.validation_error_types)
        )
        assert hashlib.sha256(record.stdout.encode()).hexdigest() == record.stdout_sha256
        assert hashlib.sha256(record.stderr.encode()).hexdigest() == record.stderr_sha256
    expected_config_names = {
        "mypy": "mypy.ini",
        "mypy-plugin": "mypy-plugin.ini",
        "pyrefly": "pyrefly.toml",
        "pyright": "pyrightconfig.json",
        "basedpyright": "pyrightconfig.json",
    }
    for checker in report.checkers:
        assert checker.stdout_sha256 == hashlib.sha256(checker.stdout.encode()).hexdigest()
        assert checker.stderr_sha256 == hashlib.sha256(checker.stderr.encode()).hexdigest()
        assert checker.command and checker.cwd == str(tmp_path.resolve())
        if checker.tool in expected_config_names:
            (receipt,) = checker.configs
            assert receipt.path == expected_config_names[checker.tool]
            assert receipt.sha256 == hashlib.sha256(receipt.contents.encode()).hexdigest()
        else:
            assert checker.tool == "ty" and not checker.configs
        if checker.tool in {"pyright", "basedpyright"}:
            probe = checker.environment_probe
            assert probe is not None
            assert probe.selected_site_packages == report.site_packages_path
            assert probe.stdout_sha256 == hashlib.sha256(probe.stdout.encode()).hexdigest()
            assert probe.stderr_sha256 == hashlib.sha256(probe.stderr.encode()).hexdigest()
        else:
            assert checker.environment_probe is None
        assert any(
            diagnostic.case_id == "strict_string_invalid" and diagnostic.severity == "error"
            for diagnostic in checker.diagnostics
        ), checker.tool
        assert not any(
            issue.case_id == "strict_valid" and issue.severity == "error"
            for issue in checker.diagnostics
        ), checker.tool

    pyright_config = next(
        record.configs[0].contents for record in report.checkers if record.tool == "pyright"
    )
    parsed_pyright_config = json.loads(pyright_config)
    assert parsed_pyright_config["venvPath"] == report.venv_path
    assert parsed_pyright_config["venv"] == report.venv_name
    assert parsed_pyright_config["typeCheckingMode"] == "strict"

    pyrefly = next(row for row in report.checkers if row.tool == "pyrefly")
    assert any(
        issue.case_id == "field_constraint_invalid" and issue.severity == "error"
        for issue in pyrefly.diagnostics
    )
    assert set(report.fixture_paths) == {case.identifier for case in CASES}
    assert len(report.fixture_paths) == len(CASES)


def test_corpus_contains_runtime_positive_and_negative_controls() -> None:
    identifiers = [case.identifier for case in CASES]
    assert len(identifiers) == len(set(identifiers))
    assert any(case.runtime_accepts for case in CASES)
    assert any(not case.runtime_accepts for case in CASES)
    assert "extra_ignore_valid" in identifiers
    assert "extra_allow_valid" in identifiers
    assert "custom_alias_generator_valid" in identifiers


@pytest.mark.parametrize(
    "script",
    [
        'raise RuntimeError("ValidationError is mentioned but not raised")',
        "raise AssertionError('intentional unrelated failure')",
        "import package_that_is_intentionally_absent_e005",
        "raise ModuleNotFoundError('deliberately missing module')",
        "raise ImportError('deliberately missing import')",
    ],
)
def test_runtime_rejects_unrelated_failures(tmp_path: Path, script: str) -> None:
    case = Case("invalid", script + "\n", False, "Adversarial runtime outcome")
    path = tmp_path / "invalid.py"
    path.write_text(case.source)
    with pytest.raises(RuntimeError, match="unexpected non-Pydantic subprocess failure"):
        _run_case(case, path, tmp_path)


def test_actual_pydantic_validation_is_structurally_recognized(tmp_path: Path) -> None:
    case = next(entry for entry in CASES if entry.identifier == "strict_string_invalid")
    path = tmp_path / "strict_string_invalid.py"
    path.write_text(case.source)
    result = _run_case(case, path, tmp_path)
    assert result.runtime_failure == "pydantic-validation"
    assert result.validation_error_types == ("int_type",)
    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "pydantic-validation"


def test_inherited_settings_and_python_optimization_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZONE", "changed-zone")
    monkeypatch.setenv("PYTHONOPTIMIZE", "1")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "injected"))
    case = next(entry for entry in CASES if entry.identifier == "settings_default_valid")
    path = tmp_path / "settings_default_valid.py"
    path.write_text(case.source)
    result = _run_case(case, path, tmp_path)
    assert result.actual_accepts
    assert not result.validation_error_types


def test_exact_case_path_and_outside_basename_rejection(tmp_path: Path) -> None:
    legitimate = tmp_path / "cases" / "strict_valid.py"
    legitimate.parent.mkdir()
    legitimate.write_text("x = 1")
    paths = {legitimate.resolve(): "strict_valid"}
    assert _known_case(str(legitimate), paths, tmp_path) == "strict_valid"
    with pytest.raises(ValueError, match="not from an exact generated fixture"):
        _known_case("/outside/corpus/strict_valid.py", paths, tmp_path)
    with pytest.raises(ValueError, match="not from an exact generated fixture"):
        _known_case(str(tmp_path / "other" / "strict_valid.py"), paths, tmp_path)


def test_text_parser_never_drops_second_uncoded_error(tmp_path: Path) -> None:
    path = tmp_path / "strict_valid.py"
    path.write_text("x = 1")
    cases = {path.resolve(): "strict_valid"}
    output = (
        f"{path}:3: error: Invalid value [arg-type]\n"
        f"{path}:4: error: Second diagnostic without a code suffix\n"
        "Found 2 errors in 1 file (checked 1 source file)\n"
    )
    parsed = _parse_text("mypy", output, cases, tmp_path)
    assert len(parsed) == 2
    assert {row.rule for row in parsed} == {"arg-type", "unclassified"}
    assert {row.line for row in parsed} == {3, 4}
    with pytest.raises(ValueError, match="Unrecognized mypy diagnostic"):
        _parse_text("mypy", output + f"{path}:5: error: truncated output [rule\n", cases, tmp_path)
    with pytest.raises(ValueError, match="not from an exact generated fixture"):
        _parse_text(
            "mypy",
            "/outside/corpus/strict_valid.py:4: error: invalid [arg-type]",
            cases,
            tmp_path,
        )


def test_ty_text_output_missing_code_is_counted(tmp_path: Path) -> None:
    path = tmp_path / "strict_valid.py"
    path.write_text("x = 1")
    parsed = _parse_text(
        "ty",
        f"{path}:3:4: error[invalid-argument-type] Bad value\n"
        f"{path}:4:5: error: Second diagnostic without code\n"
        "Found 2 diagnostics\n",
        {path.resolve(): "strict_valid"},
        tmp_path,
    )
    assert len(parsed) == 2
    assert parsed[1].rule == "unclassified"


@pytest.mark.parametrize("tool", ["pyrefly", "pyright"])
def test_malformed_json_cannot_form_valid_result(tool: str, tmp_path: Path) -> None:
    path = tmp_path / "strict_valid.py"
    path.write_text("x = 1")
    paths = {path.resolve(): "strict_valid"}
    with pytest.raises(ValueError):
        _parse_json(tool, '{"generalDiagnostics": [', paths, tmp_path)
    with pytest.raises(ValueError):
        _parse_json(tool, "{}", paths, tmp_path)


def test_json_diagnostic_cannot_escape_fixture_root(tmp_path: Path) -> None:
    path = tmp_path / "strict_valid.py"
    path.write_text("x = 1")
    with pytest.raises(ValueError, match="not from an exact generated fixture"):
        _parse_json(
            "pyrefly",
            json.dumps(
                {
                    "errors": [
                        {
                            "path": "/outside/corpus/strict_valid.py",
                            "name": "bad-argument-type",
                            "severity": "error",
                            "description": "Synthetic",
                            "line": 1,
                        }
                    ]
                }
            ),
            {path.resolve(): "strict_valid"},
            tmp_path,
        )


def test_missing_virtual_environment_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    monkeypatch.setattr(sys, "prefix", sys.base_prefix)
    with pytest.raises(RuntimeError, match="requires an active"):
        _venv()


def test_corpus_digest_includes_expectation_and_rationale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import experiments.e005.matrix as matrix

    before = _corpus_sha()
    candidate = CASES[0]
    changed = Case(
        candidate.identifier,
        candidate.source,
        not candidate.runtime_accepts,
        candidate.rationale,
    )
    monkeypatch.setattr(matrix, "CASES", (changed, *CASES[1:]))
    assert _corpus_sha() != before
    rationale_only = Case(
        candidate.identifier,
        candidate.source,
        candidate.runtime_accepts,
        candidate.rationale + " updated",
    )
    monkeypatch.setattr(matrix, "CASES", (rationale_only, *CASES[1:]))
    assert _corpus_sha() != before


@given(
    suffix=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789.-_",
        min_size=1,
        max_size=45,
    )
)
def test_unrelated_basenames_never_resolve_as_fixture(suffix: str) -> None:
    root = Path("/e005-path-fuzz")
    real = root / "cases" / "strict_valid.py"
    paths = {real.resolve(): "strict_valid"}
    unrelated = root / "outside" / suffix / "strict_valid.py"
    assert unrelated.resolve() != real.resolve()
    with pytest.raises(ValueError, match="not from an exact generated fixture"):
        _known_case(str(unrelated), paths, root)


def test_checker_reported_count_disagreement_fails(tmp_path: Path) -> None:
    path = tmp_path / "strict_valid.py"
    path.write_text("x = 1")
    files = {path.resolve(): "strict_valid"}
    with pytest.raises(ValueError, match="summary does not match"):
        _parse_text(
            "ty",
            f"{path}:3:4: error[invalid-argument-type] A problem\nFound 2 diagnostics\n",
            files,
            tmp_path,
        )
    with pytest.raises(ValueError, match="summary does not match"):
        _parse_json(
            "pyright",
            json.dumps(
                {
                    "generalDiagnostics": [],
                    "summary": {
                        "errorCount": 1,
                        "warningCount": 0,
                        "informationCount": 0,
                    },
                }
            ),
            files,
            tmp_path,
        )


@pytest.mark.parametrize(
    ("exit_code", "output"),
    [
        (1, ""),
        (1, "some other text\n"),
        (0, "cases/strict_valid.py:4: error: Invalid type [arg-type]\n"),
    ],
)
def test_exit_status_must_agree_with_normalized_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
    output: str,
) -> None:
    import subprocess

    import experiments.e005.matrix as matrix

    path = tmp_path / "cases" / "strict_valid.py"
    path.parent.mkdir()
    path.write_text("x = 1")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=(), returncode=exit_code, stdout=output, stderr=""
        ),
    )
    with pytest.raises(RuntimeError, match=r"no parsable errors|exited 0"):
        matrix._invoke(
            "mypy",
            ["fake-mypy"],
            {path.resolve(): "strict_valid"},
            tmp_path,
            (),
            matrix._checker_environment(tmp_path),
        )


def test_pyrefly_stderr_count_must_agree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    import experiments.e005.matrix as matrix

    path = tmp_path / "cases" / "strict_valid.py"
    path.parent.mkdir()
    path.write_text("x = 1")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=(), returncode=1, stdout='{"errors": []}', stderr=" INFO 2 errors\n"
        ),
    )
    with pytest.raises(RuntimeError, match="stderr error count disagrees"):
        matrix._invoke(
            "pyrefly",
            ["fake-pyrefly"],
            {path.resolve(): "strict_valid"},
            tmp_path,
            (),
            matrix._checker_environment(tmp_path),
        )


def test_runtime_subprocess_malformed_payload_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    case = Case("invalid", "x = 1\n", False, "Synthetic")
    path = tmp_path / "invalid.py"
    path.write_text(case.source)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=(), returncode=0, stdout="truncated-json {", stderr=""
        ),
    )
    with pytest.raises(RuntimeError, match="malformed runtime result"):
        _run_case(case, path, tmp_path)


def test_pyright_probe_rejects_wrong_site_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    import experiments.e005.matrix as matrix

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=(),
            returncode=1,
            stdout="Search paths for import resolution:\n/other/venv/site-packages\n",
            stderr="",
        ),
    )
    with pytest.raises(RuntimeError, match="intended site-packages absent"):
        matrix._check_pyright_environment(
            "pyright",
            "fake-pyright",
            tmp_path,
            tmp_path / "expected" / "lib" / "site-packages",
            matrix._checker_environment(tmp_path),
        )


def test_r2_mypypath_import_override_is_not_an_implicit_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Independent R2 falsifier: two incompatible stubs, identical source/config."""
    import os
    import subprocess

    import experiments.e005.matrix as matrix

    source = tmp_path / "counterexample.py"
    source.write_text(
        "from demo_stubs import make_value\nvalue: int = make_value()\n",
        encoding="utf-8",
    )
    config = tmp_path / "mypy.ini"
    config.write_text("[mypy]\npython_version = 3.14\nstrict = True\n")
    cmd = [
        matrix._exe("mypy"),
        "--config-file",
        str(config),
        "--no-incremental",
        "--no-error-summary",
        "--show-error-codes",
        str(source),
    ]
    controlled = matrix._checker_environment(tmp_path)
    files = {source.resolve(): "counterexample"}
    outputs: list[tuple[int, str, str]] = []
    unsanitized_outcomes: list[int] = []
    for label, annotation in (("int", "int"), ("str", "str")):
        stub_dir = tmp_path / label
        stub_dir.mkdir()
        (stub_dir / "demo_stubs.pyi").write_text(f"def make_value() -> {annotation}: ...\n")
        monkeypatch.setenv("MYPYPATH", str(stub_dir))
        monkeypatch.setenv("PYTHONPATH", str(stub_dir))
        # Prove the old counterexample truly changes mypy under the same
        # command/cwd/config, without forwarding the ambient test machine env.
        untrusted = {**controlled.variables, "MYPYPATH": str(stub_dir)}
        old = subprocess.run(
            cmd,
            cwd=tmp_path,
            env=untrusted,
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
        unsanitized_outcomes.append(old.returncode)

        corrected = matrix._invoke(
            "mypy",
            cmd,
            files,
            tmp_path,
            (matrix._receipt(config, tmp_path),),
            controlled,
        )
        assert corrected.checker_environment_sha256 == controlled.sha256
        assert corrected.command == tuple(cmd)
        assert corrected.configs[0].sha256 == matrix._receipt(config, tmp_path).sha256
        outputs.append((corrected.exit_code, corrected.stdout, corrected.stderr))
    assert unsanitized_outcomes == [0, 1]
    assert outputs[0] == outputs[1]
    assert outputs[0][0] == 1  # Imported module is absent in controlled path.
    assert "MYPYPATH" not in controlled.variables
    assert "PYTHONPATH" not in controlled.variables
    assert "MYPYPATH" not in os.environ or os.environ["MYPYPATH"] == str(stub_dir)
    assert controlled.policy == "e005-checker-environment-v1"


def test_r2_all_checkers_and_pyright_probes_use_identical_filtered_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import collections
    import os
    import subprocess
    import sys

    secret_marker = "E005_R2_SENSITIVE_VALUE_DO_NOT_PUBLISH"
    monkeypatch.setenv("MYPYPATH", str(tmp_path / "untrusted-mypy"))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "untrusted-python"))
    monkeypatch.setenv("NODE_OPTIONS", "--require=/untrusted/extension.js")
    monkeypatch.setenv("PYRIGHT_PYTHON_FORCE_VERSION", "0.0.0")
    monkeypatch.setenv("E005_PRIVATE_TOKEN", secret_marker)
    monkeypatch.setenv("HOME", secret_marker)
    monkeypatch.setenv("PATH", secret_marker + os.pathsep + os.environ["PATH"])

    called: list[tuple[str, dict[str, str] | None, bool]] = []
    real_run = subprocess.run

    def intercept(
        args: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        text: bool = True,
        capture_output: bool = True,
        check: bool = False,
        timeout: int = 90,
    ) -> subprocess.CompletedProcess[str]:
        name = Path(args[0]).name
        if name in {"mypy", "pyrefly", "pyright", "basedpyright", "ty"}:
            assert env is not None
            called.append((name, env.copy(), "--verbose" in args))
        return real_run(
            args,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=capture_output,
            check=check,
            timeout=timeout,
        )

    monkeypatch.setattr(subprocess, "run", intercept)
    report = execute_matrix(tmp_path)
    counts = collections.Counter(tool for tool, _, _ in called)
    assert counts == {
        "mypy": 2,
        "pyrefly": 1,
        "pyright": 2,
        "basedpyright": 2,
        "ty": 1,
    }
    assert sum(probe for _, _, probe in called) == 2
    controlled = report.checker_environment
    assert controlled.policy == "e005-checker-environment-v1"
    assert "E005_PRIVATE_TOKEN" not in controlled.variables
    assert secret_marker not in report.model_dump_json()
    for _, effective, _ in called:
        assert effective == controlled.variables
        assert effective is not None
        for prohibited in (
            "MYPYPATH",
            "PYTHONPATH",
            "NODE_OPTIONS",
            "PYRIGHT_PYTHON_FORCE_VERSION",
            "E005_PRIVATE_TOKEN",
        ):
            assert prohibited not in effective
        assert effective["HOME"] != secret_marker
        assert effective["PATH"] != secret_marker
        assert effective["VIRTUAL_ENV"] == str(Path(sys.prefix).absolute())

    assert report.schema_version == "e005-matrix-v2"
    import hashlib

    canonical = json.dumps(
        {"policy": controlled.policy, "variables": controlled.variables},
        sort_keys=True,
        separators=(",", ":"),
    )
    assert hashlib.sha256(canonical.encode()).hexdigest() == controlled.sha256
    for checker in report.checkers:
        assert checker.checker_environment_sha256 == controlled.sha256
        if checker.environment_probe is not None:
            assert checker.environment_probe.checker_environment_sha256 == controlled.sha256
    assert report.fixture_sha256 == (
        "35f2bdbfaa12e30d3af0c93fcb3dd84456cf5ad60d7d1c07e52fe38dfc95de08"
    )


def test_r2_checker_executable_is_from_active_venv() -> None:
    import sys

    import experiments.e005.matrix as matrix

    for name in ("mypy", "pyrefly", "pyright", "basedpyright", "ty"):
        executable = Path(matrix._exe(name))
        assert executable.is_relative_to(Path(sys.prefix))
        assert executable.is_file()
