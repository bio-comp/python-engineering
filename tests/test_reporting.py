"""Contract, known-bad, output consistency and render regression tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from pypdf import PdfReader

from python_engineering.reporting.analysis import analyze, condition_metrics
from python_engineering.reporting.cli import build_report, compare_runs, load_run
from python_engineering.reporting.models import Observation, ObservationState, Run
from python_engineering.reporting.render import render_markdown, report_tables
from python_engineering.reporting.scorecards import CATEGORY_PROFILES

ROOT = Path(__file__).resolve().parents[1]
MEASURED = ROOT / "examples" / "synthetic_900.json"
BLOCKED = ROOT / "examples" / "synthetic_901.json"


@pytest.fixture
def demo() -> Run:
    return load_run(MEASURED)


def mutant(run: Run) -> dict[str, object]:
    return run.model_dump(mode="json")


def _validate(raw: dict[str, object]) -> Run:
    return Run.model_validate_json(json.dumps(raw))


def test_frozen_example_is_synthetic_and_timestamp_aware(demo: Run) -> None:
    assert demo.synthetic_demonstration
    assert demo.experiment.executed_at.utcoffset() is not None
    assert demo.environment.python_version.count(".") >= 2
    assert len(demo.environment.commit_sha) == 40
    assert demo.environment.interpreter_executable.startswith("/")


def test_schema_has_explicit_version_and_forbids_extra(demo: Run) -> None:
    raw = mutant(demo)
    raw["untrusted-extra"] = "sneak"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        _validate(raw)
    assert Run.model_json_schema()["properties"]["schema_version"]["const"] == "1.0"


def test_unmeasured_outcomes_cannot_pretend_to_be_observed(demo: Run) -> None:
    raw = mutant(demo)
    obs = raw["observations"]
    assert isinstance(obs, list)
    assert isinstance(obs[0], dict)
    obs[0]["state"] = "NOT MEASURED"
    with pytest.raises(ValidationError, match="unmeasured observations"):
        _validate(raw)


def test_measured_must_contain_an_actual_result(demo: Run) -> None:
    raw = mutant(demo)
    obs = raw["observations"]
    assert isinstance(obs, list)
    assert isinstance(obs[0], dict)
    obs[0]["expected_defect"] = None
    obs[0]["detected_defect"] = None
    obs[0]["duration_ms"] = None
    with pytest.raises(ValidationError, match="measured observation requires"):
        _validate(raw)


def test_duplicate_case_ordinal_seed_rejected(demo: Run) -> None:
    raw = mutant(demo)
    obs = raw["observations"]
    assert isinstance(obs, list)
    obs.append(obs[0] | {"observation_id": "new-duplicate-id"})
    with pytest.raises(ValidationError, match="duplicate observation case"):
        _validate(raw)


def test_duplicate_evidence_rejected(demo: Run) -> None:
    raw = mutant(demo)
    evidence = raw["evidence"]
    assert isinstance(evidence, list)
    evidence.append(evidence[0])
    with pytest.raises(ValidationError, match="duplicate evidence IDs"):
        _validate(raw)


def test_unknown_receipt_rejected(demo: Run) -> None:
    raw = mutant(demo)
    obs = raw["observations"]
    assert isinstance(obs, list)
    assert isinstance(obs[0], dict)
    obs[0]["evidence_id"] = "missing-001"
    with pytest.raises(ValidationError, match="unknown evidence"):
        _validate(raw)


def test_naive_execution_timestamp_rejected(demo: Run) -> None:
    raw = mutant(demo)
    experiment = raw["experiment"]
    assert isinstance(experiment, dict)
    experiment["executed_at"] = "2026-11-17T20:00:00"
    with pytest.raises(ValidationError, match="explicit UTC offset"):
        _validate(raw)


def test_non_monotonic_thresholds_rejected(demo: Run) -> None:
    raw = mutant(demo)
    criteria = raw["criteria"]
    assert isinstance(criteria, list)
    assert isinstance(criteria[0], dict)
    criteria[0]["thresholds"] = [0.5, 0.9, 0.8, 0.95]
    with pytest.raises(ValidationError, match="strictly ascending"):
        _validate(raw)


def test_passed_gate_requires_a_real_receipt(demo: Run) -> None:
    raw = mutant(demo)
    gates = raw["gates"]
    assert isinstance(gates, list)
    assert isinstance(gates[0], dict)
    gates[0]["passed"] = True
    gates[0]["evidence_ids"] = []
    with pytest.raises(ValidationError, match="passed gate"):
        _validate(raw)


def test_conflicting_paired_truth_rejected_during_analysis(demo: Run) -> None:
    raw = mutant(demo)
    obs = raw["observations"]
    assert isinstance(obs, list)
    assert isinstance(obs[1], dict)
    obs[1]["expected_defect"] = not obs[1]["expected_defect"]
    changed = _validate(raw)
    with pytest.raises(ValueError, match="paired oracle conflict"):
        analyze(changed)


def test_score_is_mechanical_not_an_efficacy_or_evidence_grade_claim(demo: Run) -> None:
    analysis = analyze(demo)
    assert analysis.candidate.tp == 18
    assert analysis.candidate.fp == 2
    assert analysis.candidate.tn == 42
    assert analysis.candidate.fn == 3
    assert analysis.candidate.precision == pytest.approx(0.9)
    assert analysis.paired.unique_true_positives >= 0
    precision = next(c for c in analysis.criteria if c.criterion_id == "C-precision")
    assert precision.score == 3
    assert precision.evidence_grade == "synthetic_demonstration"
    assert analysis.essential_gate_state == "UNKNOWN - NOT QUALIFIED"


def test_blocked_and_missing_are_not_zeros() -> None:
    run = load_run(BLOCKED)
    analysis = analyze(run)
    assert analysis.candidate.accuracy is None
    assert all(c.score is None for c in analysis.criteria)
    assert all(c.state == ObservationState.INSUFFICIENT for c in analysis.criteria)
    assert analysis.essential_gate_state == "FAILED - NONCOMPENSATORY"
    assert "NOT MEASURED" in render_markdown(run, analysis, detailed=True)


def test_markdown_tables_use_same_derived_analysis(demo: Run) -> None:
    analysis = analyze(demo)
    summary = render_markdown(demo, analysis, detailed=False)
    detailed = render_markdown(demo, analysis, detailed=True)
    assert "0.900" in summary
    assert "0.900" in detailed
    assert "synthetic" in summary.lower()
    assert "Standard experimental evidence checklist" in detailed
    assert "independently_reproduced" not in summary
    assert len(report_tables(demo, analysis)) >= 10
    assert "SYN-001" in detailed


def test_compare_fails_closed_on_different_experiment(demo: Run) -> None:
    with pytest.raises(ValueError, match="incomparable"):
        compare_runs(demo, load_run(BLOCKED))
    comparison = compare_runs(demo, demo)
    assert "Difference" in comparison
    assert "0" in comparison


def test_immutable_output_bundle_and_sha256(tmp_path: Path) -> None:
    target = tmp_path / "rendered"
    assert build_report(MEASURED, target) == target / "manifest.json"
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["synthetic_demonstration"] is True
    assert manifest["generator_version"] == "0.1.0"
    assert manifest["input_sha256"] == hashlib.sha256(MEASURED.read_bytes()).hexdigest()
    for name, digest in manifest["files_sha256"].items():
        assert hashlib.sha256((target / name).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        build_report(MEASURED, target)


def test_pdf_paginated_selectable_and_links(tmp_path: Path) -> None:
    target = tmp_path / "pdf"
    build_report(MEASURED, target)
    reader = PdfReader(target / "report.pdf")
    assert len(reader.pages) >= 5
    page_texts = [page.extract_text() or "" for page in reader.pages]
    assert "NOT A REAL TOOL RESULT" in page_texts[0]
    assert "Observed execution provenance" not in page_texts[0]
    assert any("Git commit" in page for page in page_texts)
    assert sum("Observation / case" in page for page in page_texts) >= 2
    for text_page in page_texts:
        if "Noncompensatory acceptance gates" in text_page:
            assert "Gate\nOutcome" in text_page
    assert all(f"Page {i}" in page for i, page in enumerate(page_texts, 1))
    assert "0.900" in "".join(page_texts)
    links = []
    for page in reader.pages:
        for annotation in page.get("/Annots", []):
            item = annotation.get_object()
            if "/A" in item and "/URI" in item["/A"]:
                links.append(str(item["/A"]["/URI"]))
    assert "https://docs.reportlab.com/reportlab/userguide/ch7_tables/" in links


def test_reportlab_pdf_bytes_reproduce_from_identical_frozen_input(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_report(MEASURED, first)
    build_report(MEASURED, second)
    assert (first / "report.pdf").read_bytes() == (second / "report.pdf").read_bytes()
    assert (first / "report.md").read_bytes() == (second / "report.md").read_bytes()


def test_category_profiles_do_not_invent_prespecified_thresholds() -> None:
    assert len(CATEGORY_PROFILES) >= 7
    unique = {p.category_id for p in CATEGORY_PROFILES}
    assert len(unique) == len(CATEGORY_PROFILES)
    assert "citation_verification" in unique
    assert "coding_agent_retrieval" in unique
    assert "claim" in " ".join(CATEGORY_PROFILES[5].required_questions).lower()


@settings(max_examples=30)
@given(
    tp=st.integers(min_value=0, max_value=12),
    fp=st.integers(min_value=0, max_value=12),
    tn=st.integers(min_value=0, max_value=12),
    fn=st.integers(min_value=0, max_value=12),
)
def test_confusion_counts_match_independent_construction(
    tp: int, fp: int, tn: int, fn: int
) -> None:
    entries: list[Observation] = []
    cases = [(True, True)] * tp + [(False, True)] * fp
    cases += [(False, False)] * tn + [(True, False)] * fn
    for index, (expected, detected) in enumerate(cases):
        entries.append(
            Observation(
                observation_id=f"test-{index}",
                condition_id="candidate",
                case_id=f"case-{index}",
                state=ObservationState.MEASURED,
                evidence_id="fixture-001",
                expected_defect=expected,
                detected_defect=detected,
            )
        )
    got = condition_metrics(tuple(entries), "candidate")
    assert (got.tp, got.fp, got.tn, got.fn) == (tp, fp, tn, fn)
    assert got.detection_rows == tp + fp + tn + fn
    assert got.precision == (tp / (tp + fp) if tp + fp else None)


def test_sensitive_environment_and_raw_command_secrets_rejected(demo: Run) -> None:
    raw = mutant(demo)
    env = raw["environment"]
    assert isinstance(env, dict)
    env["selected_environment"] = {"SERVICE_API_KEY": "not-for-publication"}
    with pytest.raises(ValidationError, match="credential-like"):
        _validate(raw)
    env["selected_environment"] = {"MY_SETTING": "sk-123456789abcdefghijkl"}
    with pytest.raises(ValidationError, match="token-like"):
        _validate(raw)
    env["selected_environment"] = {}
    env["commands"] = ["upstream --api-key=secrets_should_not_be_logged"]
    with pytest.raises(ValidationError, match="unredacted credential"):
        _validate(raw)


def test_nonfinite_and_wrong_scope_criterion_rejected(demo: Run) -> None:
    raw = mutant(demo)
    criteria = raw["criteria"]
    assert isinstance(criteria, list)
    assert isinstance(criteria[0], dict)
    criteria[0]["thresholds"] = [0.5, 0.7, float("inf"), 0.95]
    with pytest.raises(ValidationError, match="thresholds"):
        _validate(raw)
    criteria[0]["thresholds"] = [0.5, 0.7, 0.85, 0.95]
    criteria[0]["metric"] = "unique_true_positives"
    criteria[0]["condition_id"] = "baseline"
    with pytest.raises(ValidationError, match="candidate incremental"):
        _validate(raw)


def test_all_cli_commands_and_entrypoint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import runpy
    import sys

    from python_engineering.reporting.cli import main

    assert main(["validate-run", str(MEASURED)]) == 0
    assert "VALID: E-900" in capsys.readouterr().out
    assert main(["score-run", str(BLOCKED)]) == 0
    assert '"score": null' in capsys.readouterr().out
    assert main(["compare-runs", str(MEASURED), str(MEASURED)]) == 0
    assert "Difference" in capsys.readouterr().out
    out = tmp_path / "created-by-cli"
    assert main(["build-report", str(BLOCKED), str(out)]) == 0
    assert "BUILT" in capsys.readouterr().out
    assert (out / "report.pdf").is_file()

    monkeypatch.setattr(sys, "argv", ["python_engineering.reporting", "validate-run", str(BLOCKED)])
    with pytest.raises(SystemExit) as status:
        runpy.run_module("python_engineering.reporting", run_name="__main__")
    assert status.value.code == 0
    assert "VALID: E-901" in capsys.readouterr().out


def test_unmeasured_partial_fields_rejected(demo: Run) -> None:
    raw = mutant(demo)
    obs = raw["observations"]
    assert isinstance(obs, list)
    assert isinstance(obs[0], dict)
    obs[0]["detected_defect"] = None
    with pytest.raises(ValidationError, match="must occur together"):
        _validate(raw)


def test_scoring_threshold_exact_endpoints(demo: Run) -> None:
    from python_engineering.reporting.models import Criterion

    criterion = Criterion(
        criterion_id="C-edge",
        category="static_typing",
        dimension="robustness",
        question="Fraction of correct cases",
        metric="accuracy",
        condition_id="candidate",
        direction="higher",
        thresholds=(0.5, 0.7, 0.85, 0.95),
        anchors=("0 below half", "1 half", "2 70%", "3 85%", "4 95%"),
    )
    result = analyze(demo.model_copy(update={"criteria": (criterion,)}))
    assert result.criteria[0].score == 3
    assert result.criteria[0].denominator == 65
