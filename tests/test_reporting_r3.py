"""Self-review R3 regression controls: empirical provenance and actual PDF glyph coverage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pypdf import PdfReader

from python_engineering.reporting.analysis import analyze
from python_engineering.reporting.cli import build_report, load_run
from python_engineering.reporting.models import EvidenceGrade, Run

DEMO = Path(__file__).resolve().parents[1] / "examples" / "synthetic_900.json"


@pytest.fixture
def run() -> Run:
    return load_run(DEMO)


def _gated_declared(run: Run, grade: EvidenceGrade) -> Run:
    evidence = tuple(
        e.model_copy(update={"grade": grade}) if e.evidence_id == "SYN-001" else e
        for e in run.evidence
    )
    gates = tuple(
        gate.model_copy(update={"passed": True, "evidence_ids": ("DOC-001",)}) for gate in run.gates
    )
    candidate = run.model_copy(
        update={"evidence": evidence, "gates": gates, "synthetic_demonstration": False}
    )
    return Run.model_validate_json(candidate.model_dump_json())


@pytest.mark.parametrize("grade", [EvidenceGrade.DOCUMENTATION, EvidenceGrade.ANECDOTAL])
def test_r3_nonempirical_only_fails_readiness_even_with_passed_gates(
    run: Run, tmp_path: Path, grade: EvidenceGrade
) -> None:
    valid = _gated_declared(run, grade)
    analysis = analyze(valid)
    assert analysis.required_criteria_state.startswith("COMPLETE")
    assert analysis.essential_gate_state.startswith("ALL RECORDED GATES PASSED")
    assert (
        analysis.evidence_classification == "NONEMPIRICAL-ONLY MEASURED DECLARATIONS - NOT ATTESTED"
    )
    assert analysis.evaluation_readiness == "INCOMPLETE - NONEMPIRICAL MEASURED EVIDENCE"
    source = tmp_path / "input.json"
    source.write_text(valid.model_dump_json())
    target = tmp_path / "report"
    build_report(source, target)
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["evidence_classification"] == analysis.evidence_classification
    assert manifest["synthetic_demonstration"] is False
    for name in ("summary.md", "report.md"):
        content = (target / name).read_text()
        assert analysis.evidence_classification in content
        assert analysis.evaluation_readiness in content
        assert "NONEMPIRICAL" in content
    pdf_text = "".join(page.extract_text() or "" for page in PdfReader(target / "report.pdf").pages)
    assert analysis.evidence_classification in pdf_text
    assert analysis.evaluation_readiness in pdf_text
    for name, digest in manifest["files_sha256"].items():
        assert hashlib.sha256((target / name).read_bytes()).hexdigest() == digest


def test_r3_mixed_empirical_and_nonempirical_measured_cannot_claim_readiness(
    run: Run, tmp_path: Path
) -> None:
    base = _gated_declared(run, EvidenceGrade.INDEPENDENT)
    changed = list(base.observations)
    changed[0] = changed[0].model_copy(update={"evidence_id": "DOC-001"})
    valid = Run.model_validate_json(
        base.model_copy(update={"observations": tuple(changed)}).model_dump_json()
    )
    analysis = analyze(valid)
    assert analysis.evidence_classification == (
        "MIXED EMPIRICAL AND NONEMPIRICAL DECLARATIONS - NOT ATTESTED"
    )
    assert analysis.evaluation_readiness == (
        "INCOMPLETE - MIXED EMPIRICAL AND NONEMPIRICAL EVIDENCE"
    )
    source = tmp_path / "mixed.json"
    source.write_text(valid.model_dump_json())
    dest = tmp_path / "mixed-bundle"
    build_report(source, dest)
    manifest = json.loads((dest / "manifest.json").read_text())
    assert manifest["evidence_classification"] == analysis.evidence_classification
    assert manifest["synthetic_demonstration"] is False
    assert "MIXED EMPIRICAL / NONEMPIRICAL" in (dest / "summary.md").read_text()
    assert "MIXED EMPIRICAL / NONEMPIRICAL" in (dest / "report.md").read_text()
    assert "MIXED EMPIRICAL / NONEMPIRICAL" in "".join(
        page.extract_text() or "" for page in PdfReader(dest / "report.pdf").pages
    )
    assert "MIXED SYNTHETIC" not in (dest / "summary.md").read_text()
    for name, digest in manifest["files_sha256"].items():
        assert hashlib.sha256((dest / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize(
    "grade",
    [EvidenceGrade.PILOT, EvidenceGrade.CONTROLLED, EvidenceGrade.INDEPENDENT],
)
def test_r3_empirical_source_declared_grade_retains_recorded_readiness(
    run: Run, grade: EvidenceGrade
) -> None:
    valid = _gated_declared(run, grade)
    analysis = analyze(valid)
    assert analysis.evidence_classification == "NONSYNTHETIC SOURCE DECLARATIONS - NOT ATTESTED"
    assert analysis.evaluation_readiness == "RECORDED REQUIREMENTS MET - NO ADOPTION INFERRED"


@pytest.mark.parametrize("glyph", ["∅", "≡", "\u2217"])
def test_r3_glyph_zero_cannot_publish_fake_supported_unicode(
    run: Run, tmp_path: Path, glyph: str
) -> None:
    source = tmp_path / "input.json"
    source.write_text(
        run.model_copy(update={"rubric_revision": "rubric-v1 " + glyph}).model_dump_json()
    )
    dest = tmp_path / "bundle"
    with pytest.raises(ValueError, match="PDF font does not support input glyphs"):
        build_report(source, dest)
    assert not dest.exists()
    assert not list(tmp_path.glob(".bundle.staging-*"))


@pytest.mark.parametrize("char", ["\n", "\r", "\t", "\u0085"])
def test_r3_footer_control_codes_rejected_before_publication(
    run: Run, tmp_path: Path, char: str
) -> None:
    source = tmp_path / "input.json"
    source.write_text(
        run.model_copy(update={"rubric_revision": "rubric-v1" + char + "suffix"}).model_dump_json()
    )
    dest = tmp_path / "bundle"
    with pytest.raises((ValueError, ValidationError), match=r"control|PDF"):
        build_report(source, dest)
    assert not dest.exists()
    assert not list(tmp_path.glob(".bundle.staging-*"))
