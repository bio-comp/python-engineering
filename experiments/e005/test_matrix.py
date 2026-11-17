"""E-005 independent synthetic runtime and checker comparator protocol."""

from pathlib import Path

from experiments.e005.cases import CASES
from experiments.e005.matrix import execute_matrix


def test_all_synthetic_contracts_and_checker_outputs(tmp_path: Path) -> None:
    report = execute_matrix(tmp_path)
    assert len(report.runtimes) == len(CASES) == 16
    assert all(row.actual_accepts == row.expected_accepts for row in report.runtimes)
    assert len(report.fixture_sha256) == 64
    assert [row.tool for row in report.checkers] == [
        "mypy",
        "mypy-plugin",
        "pyrefly",
        "pyright",
        "basedpyright",
        "ty",
    ]

    # Establish at least one independent hard false-negative control for
    # each checker: the exact invalid strict constructor from Pydantic runtime.
    for checker in report.checkers:
        assert any(
            diagnostic.case_id == "strict_string_invalid" and diagnostic.severity == "error"
            for diagnostic in checker.diagnostics
        ), checker.tool

    # Pin Pyrefly's vendor-documented special capability to an executable
    # boundary; the other checkers are measured, not forced to agree.
    pyrefly = next(row for row in report.checkers if row.tool == "pyrefly")
    assert any(
        issue.case_id == "field_constraint_invalid" and issue.severity == "error"
        for issue in pyrefly.diagnostics
    )

    # A correctly typed strict constructor must remain accepted by all.
    for checker in report.checkers:
        assert not any(
            issue.case_id == "strict_valid" and issue.severity == "error"
            for issue in checker.diagnostics
        ), checker.tool


def test_corpus_contains_runtime_positive_and_negative_controls() -> None:
    identifiers = [case.identifier for case in CASES]
    assert len(identifiers) == len(set(identifiers))
    assert any(case.runtime_accepts for case in CASES)
    assert any(not case.runtime_accepts for case in CASES)
    assert "extra_ignore_valid" in identifiers
    assert "extra_allow_valid" in identifiers
    assert "custom_alias_generator_valid" in identifiers
