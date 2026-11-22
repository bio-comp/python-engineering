"""R1-R7 regression corpus: adversarial examples previously passed the R1-reviewed HEAD."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pypdf import PdfReader

from python_engineering.reporting.analysis import analyze
from python_engineering.reporting.cli import build_report, compare_runs, load_run, main
from python_engineering.reporting.integrity import (
    ReceiptStatus,
    assert_no_local_failures,
    verify_receipts,
)
from python_engineering.reporting.models import EvidenceGrade, ObservationState, Run
from python_engineering.reporting.render import render_markdown, report_tables

ROOT = Path(__file__).resolve().parents[1]
DEMO_FILE = ROOT / "examples" / "synthetic_900.json"


@pytest.fixture
def run() -> Run:
    return load_run(DEMO_FILE)


def frozen_mutation(path: Path, run: Run) -> Path:
    path.write_text(run.model_dump_json(indent=2) + "\n")
    return path


@pytest.mark.parametrize("note_length", [4000, 12000])
def test_r1_oversized_evidence_row_splits_without_truncation(
    run: Run, tmp_path: Path, note_length: int
) -> None:
    marker = "FULL-CONTENT-START " + ("Q" * note_length) + " FULL-CONTENT-END"
    evidence = run.evidence[0].model_copy(update={"note": marker})
    changed = run.model_copy(update={"evidence": (evidence, *run.evidence[1:])})
    source = frozen_mutation(tmp_path / "valid-note.json", changed)
    target = tmp_path / "output"
    assert build_report(source, target).is_file()
    reader = PdfReader(target / "report.pdf")
    text = "".join(page.extract_text() or "" for page in reader.pages)
    assert text.count("Q") >= note_length
    assert "FULL-CONTENT-START" in "".join(text.split())
    assert "FULL-CONTENT-END" in "".join(text.split())
    assert "Evidence receipts" in text
    assert len(reader.pages) >= 12
    assert (target / "manifest.json").exists()
    assert (target / "evidence_verification.json").exists()


def test_r1_pdf_exception_does_not_publish_partial_bundle(
    run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import python_engineering.reporting.cli as cli

    def crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected PDF failure")

    monkeypatch.setattr(cli, "render_pdf", crash)
    target = tmp_path / "published"
    with pytest.raises(RuntimeError, match="injected PDF"):
        build_report(DEMO_FILE, target)
    assert not target.exists()
    assert not list(tmp_path.glob(".published.staging-*"))


def test_r1_successful_bundle_cannot_be_overwritten(run: Run, tmp_path: Path) -> None:
    target = tmp_path / "published"
    build_report(DEMO_FILE, target)
    digest = hashlib.sha256((target / "report.pdf").read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        build_report(DEMO_FILE, target)
    assert hashlib.sha256((target / "report.pdf").read_bytes()).hexdigest() == digest


def test_r2_drop_observation_fails_before_performance_comparison(run: Run) -> None:
    modified = run.model_copy(update={"observations": run.observations[:-1]})
    with pytest.raises(ValueError, match="incomparable observation populations"):
        compare_runs(run, modified)


def test_r2_changed_case_and_state_oracle_fails(run: Run) -> None:
    observations = list(run.observations)
    observations[1] = observations[1].model_copy(update={"case_id": "mutated-new-case-id"})
    with pytest.raises(ValueError, match="incomparable observation populations"):
        compare_runs(run, run.model_copy(update={"observations": tuple(observations)}))
    observations = list(run.observations)
    observations[1] = observations[1].model_copy(
        update={"expected_defect": not observations[1].expected_defect}
    )
    with pytest.raises(ValueError, match="changed state/oracle"):
        compare_runs(run, run.model_copy(update={"observations": tuple(observations)}))
    observations = list(run.observations)
    observations[1] = observations[1].model_copy(
        update={
            "state": ObservationState.BLOCKED,
            "expected_defect": None,
            "detected_defect": None,
        }
    )
    with pytest.raises(ValueError, match="changed state/oracle"):
        compare_runs(run, run.model_copy(update={"observations": tuple(observations)}))


def test_r2_matched_changed_prediction_is_valid_descriptive_comparison(run: Run) -> None:
    observations = list(run.observations)
    observations[1] = observations[1].model_copy(
        update={"detected_defect": not observations[1].detected_defect}
    )
    changed = Run.model_validate_json(
        run.model_copy(update={"observations": tuple(observations)}).model_dump_json()
    )
    result = compare_runs(run, changed)
    assert "Matched descriptive run comparison" in result
    assert "Changed predictions are allowed" in result
    assert "incomparable" not in result


def test_r3_oracle_conflict_rejected_by_run_and_validate_cli(run: Run, tmp_path: Path) -> None:
    observations = list(run.observations)
    observations[1] = observations[1].model_copy(
        update={"expected_defect": not observations[1].expected_defect}
    )
    source = frozen_mutation(
        tmp_path / "bad-oracle.json",
        run.model_copy(update={"observations": tuple(observations)}),
    )
    with pytest.raises(ValidationError, match="reference-oracle conflict"):
        load_run(source)
    with pytest.raises(ValidationError, match="reference-oracle conflict"):
        main(["validate-run", str(source)])


def test_r3_repeat_with_same_case_and_different_truth_rejected(run: Run) -> None:
    observations = list(run.observations)
    observations.append(
        observations[0].model_copy(
            update={
                "observation_id": "new-repeat",
                "repetition": 1,
                "expected_defect": not observations[0].expected_defect,
            }
        )
    )
    with pytest.raises(ValidationError, match="reference-oracle conflict"):
        Run.model_validate_json(
            run.model_copy(update={"observations": tuple(observations)}).model_dump_json()
        )


def test_r4_passed_gates_do_not_hide_required_missing_results(run: Run) -> None:
    passed = tuple(
        g.model_copy(update={"passed": True, "evidence_ids": ("SYN-001",)}) for g in run.gates
    )
    missing = run.model_copy(update={"observations": (), "gates": passed})
    analysis = analyze(missing)
    assert "ALL RECORDED GATES PASSED" in analysis.essential_gate_state
    assert analysis.required_criteria_state.startswith("INCOMPLETE")
    assert analysis.evaluation_readiness == "INCOMPLETE - REQUIRED MEASUREMENTS"
    assert len(analysis.unscored_required_criteria) == 2
    md = render_markdown(missing, analysis, detailed=True)
    assert "INCOMPLETE - REQUIRED MEASUREMENTS" in md
    assert "Required-criterion completeness" in md


def test_r4_optional_unscored_criterion_does_not_block_required(run: Run) -> None:
    optional = run.criteria[0].model_copy(
        update={"criterion_id": "optional-exploratory", "min_denominator": 10000, "required": False}
    )
    passed = tuple(
        g.model_copy(update={"passed": True, "evidence_ids": ("SYN-001",)}) for g in run.gates
    )
    changed = run.model_copy(update={"criteria": (*run.criteria, optional), "gates": passed})
    analysis = analyze(changed)
    assert analysis.criteria[-1].score is None
    assert analysis.required_criteria_state.startswith("COMPLETE")
    assert analysis.unscored_required_criteria == ()
    assert analysis.evaluation_readiness == "INCOMPLETE - SYNTHETIC DEMONSTRATION"


def test_r5_local_verified_receipt_matches_actual_bytes(run: Run) -> None:
    checks = verify_receipts(run, evidence_root=ROOT)
    assert checks[0].status == ReceiptStatus.VERIFIED_LOCAL
    assert checks[0].declared_sha256 == checks[0].observed_sha256
    assert checks[1].status == ReceiptStatus.EXTERNAL


def test_r5_modified_digest_fails_explicit_verification(run: Run, tmp_path: Path) -> None:
    receipt = run.evidence[0].model_copy(update={"source_sha256": "f" * 64})
    changed = run.model_copy(update={"evidence": (receipt, *run.evidence[1:])})
    source = frozen_mutation(tmp_path / "bad-hash.json", changed)
    checks = verify_receipts(changed, evidence_root=ROOT)
    assert checks[0].status == ReceiptStatus.MISMATCH
    with pytest.raises(ValueError, match="HASH MISMATCH"):
        assert_no_local_failures(checks)
    with pytest.raises(ValueError, match="HASH MISMATCH"):
        main(["validate-run", str(source), "--evidence-root", str(ROOT)])
    with pytest.raises(ValueError, match="HASH MISMATCH"):
        build_report(source, tmp_path / "bad-bundle", evidence_root=ROOT)
    assert not (tmp_path / "bad-bundle").exists()


def test_r5_unchecked_external_and_unavailable_are_not_verified(run: Run) -> None:
    unchecked = verify_receipts(run)
    assert all(check.status != ReceiptStatus.VERIFIED_LOCAL for check in unchecked)
    assert unchecked[0].status == ReceiptStatus.NOT_CHECKED
    assert unchecked[1].status == ReceiptStatus.EXTERNAL
    other = run.evidence[0].model_copy(update={"source": "not-real-file.txt"})
    changed = run.model_copy(update={"evidence": (other, *run.evidence[1:])})
    checks = verify_receipts(changed, evidence_root=ROOT)
    assert checks[0].status == ReceiptStatus.UNAVAILABLE


@pytest.mark.parametrize("source", ["../private.txt", "/etc/passwd", "C:\\secret.txt"])
def test_r5_unsafe_source_never_read(run: Run, source: str, tmp_path: Path) -> None:
    receipt = run.evidence[0].model_copy(update={"source": source})
    changed = run.model_copy(update={"evidence": (receipt, *run.evidence[1:])})
    checks = verify_receipts(changed, evidence_root=tmp_path)
    assert checks[0].status == ReceiptStatus.UNSAFE
    with pytest.raises(ValueError, match="UNSAFE PATH"):
        assert_no_local_failures(checks)


def test_r5_symlink_to_private_file_rejected(run: Run, tmp_path: Path) -> None:
    root = tmp_path / "permitted"
    root.mkdir()
    outside = tmp_path / "private.txt"
    outside.write_text("private unrelated bytes")
    (root / "receipt.txt").symlink_to(outside)
    receipt = run.evidence[0].model_copy(update={"source": "receipt.txt"})
    changed = run.model_copy(update={"evidence": (receipt, *run.evidence[1:])})
    assert verify_receipts(changed, evidence_root=root)[0].status == ReceiptStatus.UNSAFE


def _unicode_font() -> Path | None:
    for path in (
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ):
        if path.is_file():
            return path
    return None


def test_r6_unsupported_unicode_fails_explicitly_with_no_partial_dir(
    run: Run, tmp_path: Path
) -> None:
    text = "Greek Δ and \u03b1, Cyrillic Привет, East Asian 漢字, emoji 🚀"
    changed = run.model_copy(
        update={"interpretation": run.interpretation.model_copy(update={"summary": text})}
    )
    source = frozen_mutation(tmp_path / "unicode.json", changed)
    for font in (None, _unicode_font()):
        target = tmp_path / ("font" if font else "default")
        with pytest.raises(ValueError, match="PDF font does not support input glyphs"):
            build_report(source, target, font_path=font)
        assert not target.exists()


def test_r6_supported_scientific_unicode_is_selectable(run: Run, tmp_path: Path) -> None:
    font = _unicode_font()
    if font is None:
        pytest.skip("No explicitly approved broad Unicode system font is installed")
    text = "Greek Δ and \u03b1, Cyrillic Привет, math ± ≤ ≥ µ"
    changed = run.model_copy(
        update={"interpretation": run.interpretation.model_copy(update={"summary": text})}
    )
    source = frozen_mutation(tmp_path / "unicode-positive.json", changed)
    target = tmp_path / "font-bundle"
    build_report(source, target, font_path=font)
    recovered = "\n".join(
        page.extract_text() or "" for page in PdfReader(target / "report.pdf").pages
    )
    for piece in ("Δ", "\u03b1", "Привет", "±", "≤", "≥", "µ"):
        assert piece in recovered
    assert json.loads((target / "manifest.json").read_text())["font_sha256"] == (
        hashlib.sha256(font.read_bytes()).hexdigest()
    )


def test_r7_unrelated_independent_receipt_not_proof_of_reproduction(run: Run) -> None:
    independent = run.evidence[1].model_copy(update={"grade": EvidenceGrade.INDEPENDENT})
    changed = run.model_copy(
        update={
            "synthetic_demonstration": False,
            "observations": (),
            "evidence": (run.evidence[0], independent),
        }
    )
    table = next(
        t
        for t in report_tables(changed, analyze(changed))
        if t.title.startswith("Standard experimental")
    )
    independent_row = next(row for row in table.rows if row[0] == "Independent reproduction")
    assert independent_row[1] == "NOT MEASURED"


def test_r7_linked_positive_and_mixed_grades_not_attested(run: Run) -> None:
    linked = run.evidence[0].model_copy(update={"grade": EvidenceGrade.INDEPENDENT})
    changed = run.model_copy(
        update={
            "synthetic_demonstration": False,
            "evidence": (linked, run.evidence[1]),
        }
    )
    table = next(
        t
        for t in report_tables(changed, analyze(changed))
        if t.title.startswith("Standard experimental")
    )
    status = next(row[1] for row in table.rows if row[0] == "Independent reproduction")
    assert status == "SOURCE DECLARED - NOT ATTESTED"
    first = changed.observations[0].model_copy(update={"evidence_id": "DOC-001"})
    mixed = changed.model_copy(
        update={
            "observations": (first, *changed.observations[1:]),
        }
    )
    table = next(
        t
        for t in report_tables(mixed, analyze(mixed))
        if t.title.startswith("Standard experimental")
    )
    status = next(row[1] for row in table.rows if row[0] == "Independent reproduction")
    assert status == "MIXED SOURCE GRADES - NOT ATTESTED"


def test_r5_verified_receipts_flow_into_new_manifest_and_report(tmp_path: Path) -> None:
    target = tmp_path / "verified"
    assert main(["validate-run", str(DEMO_FILE), "--evidence-root", str(ROOT)]) == 0
    assert main(["build-report", str(DEMO_FILE), str(target), "--evidence-root", str(ROOT)]) == 0
    verified = json.loads((target / "evidence_verification.json").read_text())
    assert verified[0]["status"] == ReceiptStatus.VERIFIED_LOCAL.value
    assert verified[1]["status"] == ReceiptStatus.EXTERNAL.value
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["receipt_verification_root_supplied"] is True
    assert "evidence_verification.json" in manifest["files_sha256"]
    md = (target / "report.md").read_text()
    assert "VERIFIED LOCAL BYTES" in md
    assert "UNVERIFIED - EXTERNAL SOURCE NOT FETCHED" in md
    for name, digest in manifest["files_sha256"].items():
        assert hashlib.sha256((target / name).read_bytes()).hexdigest() == digest


def test_r6_cjk_supported_when_font_has_glyphs_else_explicit_failure(
    run: Run, tmp_path: Path
) -> None:
    from reportlab.pdfbase.ttfonts import TTFont

    font = _unicode_font()
    if font is None:
        pytest.skip("No approved broad Unicode system font installed")
    cmap = TTFont("R1-cjk-cmap", str(font)).face.charToGlyph
    text = "East Asian 漢字"
    changed = run.model_copy(
        update={"interpretation": run.interpretation.model_copy(update={"summary": text})}
    )
    source = frozen_mutation(tmp_path / "cjk.json", changed)
    target = tmp_path / "cjk-report"
    if all(ord(c) in cmap for c in "漢字"):
        build_report(source, target, font_path=font)
        recovered = "\n".join(
            page.extract_text() or "" for page in PdfReader(target / "report.pdf").pages
        )
        assert "漢字" in recovered
    else:
        with pytest.raises(ValueError, match="PDF font does not support input glyphs"):
            build_report(source, target, font_path=font)
        assert not target.exists()


def test_r3_checked_in_structural_schema_remains_exact() -> None:
    from python_engineering.reporting.models import Run

    checked_in = json.loads((ROOT / "examples" / "reporting.schema.json").read_text())
    assert checked_in == Run.model_json_schema()
