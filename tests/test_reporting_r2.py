"""Independent R2-F1/F2/F3 discriminating regressions on Issue #18 / PR #20."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pypdf import PdfReader

from python_engineering.reporting.analysis import analyze
from python_engineering.reporting.cli import build_report, load_run, main
from python_engineering.reporting.models import EvidenceGrade, Run
from python_engineering.reporting.render import render_markdown, report_tables

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "synthetic_900.json"


@pytest.fixture
def run() -> Run:
    return load_run(DEMO)


def _saved(path: Path, run: Run) -> Path:
    path.write_text(run.model_dump_json(indent=2) + "\n")
    return path


def _all_gates_pass(run: Run) -> Run:
    gates = tuple(
        gate.model_copy(update={"passed": True, "evidence_ids": ("SYN-001",)}) for gate in run.gates
    )
    return run.model_copy(update={"gates": gates})


def test_r2_f1_known_bad_all_synthetic_cannot_claim_nonsynthetic(run: Run, tmp_path: Path) -> None:
    # This validated and published as an ordinary evidence snapshot at R2-reviewed HEAD.
    bad = _all_gates_pass(run).model_copy(update={"synthetic_demonstration": False})
    source = _saved(tmp_path / "mutated-e900.json", bad)
    with pytest.raises(ValidationError, match="synthetic"):
        Run.model_validate_json(source.read_bytes())
    with pytest.raises(ValidationError, match="synthetic"):
        main(["validate-run", str(source)])
    target = tmp_path / "incorrectly-published"
    with pytest.raises(ValidationError, match="synthetic"):
        build_report(source, target)
    assert not target.exists()


def test_r2_f1_mixed_measured_receipts_are_explicit_and_incomplete(
    run: Run, tmp_path: Path
) -> None:
    independent = run.evidence[1].model_copy(update={"grade": EvidenceGrade.INDEPENDENT})
    candidate = tuple(
        item.model_copy(update={"evidence_id": "DOC-001"})
        if item.condition_id == "candidate"
        else item
        for item in run.observations
    )
    mixed = _all_gates_pass(run).model_copy(
        update={"evidence": (run.evidence[0], independent), "observations": candidate}
    )
    valid = Run.model_validate_json(mixed.model_dump_json())
    result = analyze(valid)
    assert result.evidence_classification == "MIXED SYNTHETIC AND NONSYNTHETIC DECLARATIONS"
    assert result.evaluation_readiness == "INCOMPLETE - SYNTHETIC MEASURED EVIDENCE"
    assert result.required_criteria_state.startswith("COMPLETE")
    assert "MIXED" in render_markdown(valid, result, detailed=False)
    source = _saved(tmp_path / "mixed.json", valid)
    target = tmp_path / "mixed-bundle"
    build_report(source, target)
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["evidence_classification"] == result.evidence_classification
    assert manifest["synthetic_demonstration"] is True
    assert "MIXED" in (target / "summary.md").read_text()
    assert result.evaluation_readiness in (target / "report.md").read_text()
    assert "MIXED" in "".join(
        page.extract_text() or "" for page in PdfReader(target / "report.pdf").pages
    )
    for name, digest in manifest["files_sha256"].items():
        assert hashlib.sha256((target / name).read_bytes()).hexdigest() == digest
    with pytest.raises(ValidationError, match="synthetic"):
        Run.model_validate_json(
            mixed.model_copy(update={"synthetic_demonstration": False}).model_dump_json()
        )


def test_r2_f1_declared_nonsynthetic_is_not_independent_attestation(run: Run) -> None:
    independent = run.evidence[0].model_copy(update={"grade": EvidenceGrade.INDEPENDENT})
    other = run.evidence[1]
    candidate = run.model_copy(
        update={"evidence": (independent, other), "synthetic_demonstration": False}
    )
    valid = Run.model_validate_json(candidate.model_dump_json())
    result = analyze(valid)
    assert result.evidence_classification == "NONSYNTHETIC SOURCE DECLARATIONS - NOT ATTESTED"
    assert result.evaluation_readiness != "INCOMPLETE - SYNTHETIC MEASURED EVIDENCE"


def test_r2_f2_paired_unique_true_positives_references_both_supports(run: Run) -> None:
    independent = run.evidence[1].model_copy(update={"grade": EvidenceGrade.INDEPENDENT})
    observations = tuple(
        o.model_copy(update={"evidence_id": "DOC-001"}) if o.condition_id == "candidate" else o
        for o in run.observations
    )
    unique = run.criteria[0].model_copy(
        update={"criterion_id": "C-unique", "metric": "unique_true_positives"}
    )
    mixed = run.model_copy(
        update={
            "evidence": (run.evidence[0], independent),
            "observations": observations,
            "criteria": (unique,),
        }
    )
    measured = analyze(Run.model_validate_json(mixed.model_dump_json()))
    result = measured.criteria[0]
    assert measured.paired.matched_detection_pairs == 65
    assert result.value == float(measured.paired.unique_true_positives)
    assert set(result.evidence_ids) == {"SYN-001", "DOC-001"}
    assert result.evidence_grade == "mixed (independently_reproduced, synthetic_demonstration)"
    assert "NOT ATTESTED" not in result.evidence_grade  # grades are source declarations
    table = next(
        t for t in report_tables(mixed, measured) if t.title.startswith("Criterion-level rubric")
    )
    assert "mixed (" in table.rows[0][3]


def test_r2_f2_single_condition_metric_ignores_noncontributors(run: Run) -> None:
    independent = run.evidence[1].model_copy(update={"grade": EvidenceGrade.INDEPENDENT})
    observations = tuple(
        o.model_copy(update={"evidence_id": "DOC-001"}) if o.condition_id == "candidate" else o
        for o in run.observations
    )
    candidate = list(observations)
    # TN is not part of precision's TP+FP denominator; retain it as synthetic.
    index = next(
        i
        for i, o in enumerate(candidate)
        if o.condition_id == "candidate"
        and o.expected_defect is False
        and o.detected_defect is False
    )
    candidate[index] = candidate[index].model_copy(update={"evidence_id": "SYN-001"})
    changed = run.model_copy(
        update={"evidence": (run.evidence[0], independent), "observations": tuple(candidate)}
    )
    result = analyze(Run.model_validate_json(changed.model_dump_json()))
    precision = next(c for c in result.criteria if c.metric == "precision")
    assert precision.evidence_ids == ("DOC-001",)
    assert precision.evidence_grade == "independently_reproduced"
    assert precision.value == pytest.approx(0.9)


def test_r2_f3_footer_unsupported_glyphs_fail_before_publication(run: Run, tmp_path: Path) -> None:
    bad = run.model_copy(update={"rubric_revision": "rubric-v1 漢🚀"})
    source = _saved(tmp_path / "bad-footer.json", bad)
    target = tmp_path / "bad-footer-published"
    with pytest.raises(ValueError, match="PDF font does not support input glyphs"):
        build_report(source, target)
    assert not target.exists()
    assert not list(tmp_path.glob(".bad-footer-published.staging-*"))


def test_r2_f3_supported_footer_text_is_selectable_and_manifest_consistent(
    run: Run, tmp_path: Path
) -> None:
    good = run.model_copy(update={"rubric_revision": "rubric-v1 ±"})
    source = _saved(tmp_path / "supported-footer.json", good)
    target = tmp_path / "supported-footer"
    build_report(source, target)
    pages = [page.extract_text() or "" for page in PdfReader(target / "report.pdf").pages]
    assert pages
    assert all("rubric rubric-v1 ±" in page for page in pages)
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["rubric_revision"] == good.rubric_revision


def test_r2_f1_bypassed_model_copy_still_cannot_claim_readiness(run: Run) -> None:
    # Pydantic model_copy(update=...) does not validate updates; direct
    # analysis must nevertheless classify actual measured evidence correctly.
    copied = _all_gates_pass(run).model_copy(update={"synthetic_demonstration": False})
    result = analyze(copied)
    assert result.evidence_classification == "SYNTHETIC-ONLY MEASURED EVIDENCE"
    assert result.evaluation_readiness == "INCOMPLETE - SYNTHETIC DEMONSTRATION"
    assert "SYNTHETIC" in render_markdown(copied, result, detailed=False)


def test_r2_f3_dynamic_bold_title_has_separate_cmap_check(run: Run) -> None:
    import reportlab
    from reportlab.pdfbase.ttfonts import TTFont

    from python_engineering.reporting.render import _check_pdf_repertoire

    font = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
    cmap = set(TTFont("R2-bold-title-check", str(font)).face.charToGlyph)
    assert ord("±") in cmap
    title = run.experiment.title + " ±"
    modified = run.model_copy(
        update={"experiment": run.experiment.model_copy(update={"title": title})}
    )
    with pytest.raises(ValueError, match="PDF font does not support input glyphs"):
        _check_pdf_repertoire(
            modified, analyze(modified), cmap=cmap, bold_cmap=cmap - {ord("±")}, receipt_checks=()
        )
