"""Validated reporting CLI with atomic publication and matched comparisons."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from python_engineering.reporting import REPORT_GENERATOR_VERSION
from python_engineering.reporting.analysis import analyze
from python_engineering.reporting.integrity import (
    ReceiptCheck,
    assert_no_local_failures,
    verify_receipts,
)
from python_engineering.reporting.models import Run
from python_engineering.reporting.render import (
    pdf_font_identity,
    render_markdown,
    render_pdf,
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_run(path: Path) -> Run:
    """Parse frozen input directly with Pydantic v2."""
    return Run.model_validate_json(path.read_bytes())


def _write_new(path: Path, contents: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(contents)


def _checks(run: Run, root: Path | None) -> tuple[ReceiptCheck, ...]:
    checks = verify_receipts(run, evidence_root=root)
    if root is not None:
        assert_no_local_failures(checks)
    return checks


def build_report(
    source: Path,
    target_dir: Path,
    *,
    evidence_root: Path | None = None,
    font_path: Path | None = None,
) -> Path:
    """Build fully in a hidden sibling, then publish one complete immutable directory."""
    original = source.read_bytes()
    run = Run.model_validate_json(original)
    result = analyze(run)
    checks = _checks(run, evidence_root)
    font_file, font_sha256 = pdf_font_identity(font_path)
    if target_dir.exists() or target_dir.is_symlink():
        raise FileExistsError(f"immutable report output already exists: {target_dir}")
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{target_dir.name}.staging-", dir=target_dir.parent))
    try:
        payloads = {
            "run.json": original,
            "analysis.json": (result.model_dump_json(indent=2) + "\n").encode(),
            "evidence_verification.json": (
                json.dumps([c.model_dump(mode="json") for c in checks], indent=2) + "\n"
            ).encode(),
            "summary.md": render_markdown(
                run, result, detailed=False, receipt_checks=checks
            ).encode(),
            "report.md": render_markdown(
                run, result, detailed=True, receipt_checks=checks
            ).encode(),
        }
        for name, data in payloads.items():
            _write_new(stage / name, data)
        render_pdf(run, result, stage / "report.pdf", receipt_checks=checks, font_path=font_path)
        files = sorted(
            (name, _digest((stage / name).read_bytes())) for name in (*payloads, "report.pdf")
        )
        manifest = {
            "artifact_schema": "1.0",
            "experiment_id": run.experiment.experiment_id,
            "run_id": run.experiment.run_id,
            "input_sha256": _digest(original),
            "source_commit_sha": run.environment.commit_sha,
            "schema_revision": run.schema_version,
            "rubric_revision": run.rubric_revision,
            "generator_version": REPORT_GENERATOR_VERSION,
            "status": run.experiment.status.value,
            "synthetic_demonstration": run.synthetic_demonstration,
            "evidence_classification": result.evidence_classification,
            "font_name": font_file.name,
            "font_sha256": font_sha256,
            "receipt_verification_root_supplied": evidence_root is not None,
            "files_sha256": dict(files),
        }
        _write_new(
            stage / "manifest.json",
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
        )
        # Nonempty successful bundles cannot be replaced by POSIX directory rename.
        if target_dir.exists():
            raise FileExistsError(f"immutable report output already exists: {target_dir}")
        os.rename(stage, target_dir)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target_dir / "manifest.json"


def _population(run: Run) -> dict[tuple[str, str, int, int | None], tuple[str, bool | None]]:
    return {
        (o.condition_id, o.case_id, o.repetition, o.seed): (o.state.value, o.expected_defect)
        for o in run.observations
    }


def compare_runs(left: Run, right: Run) -> str:
    """Only matched case populations support unconditional descriptive count deltas."""
    if (
        left.experiment.experiment_id != right.experiment.experiment_id
        or left.experiment.protocol_revision != right.experiment.protocol_revision
        or left.baseline != right.baseline
        or left.candidate != right.candidate
        or left.rubric_revision != right.rubric_revision
        or left.criteria != right.criteria
        or left.environment.fixture_revision != right.environment.fixture_revision
        or left.synthetic_demonstration != right.synthetic_demonstration
    ):
        raise ValueError("incomparable experiment/protocol/fixture/conditions/rubric")
    a_keys, b_keys = _population(left), _population(right)
    if a_keys != b_keys:
        only_a = set(a_keys) - set(b_keys)
        only_b = set(b_keys) - set(a_keys)
        changed = {key for key in set(a_keys) & set(b_keys) if a_keys[key] != b_keys[key]}
        raise ValueError(
            "incomparable observation populations: "
            f"missing={len(only_a)}, added={len(only_b)}, "
            f"changed state/oracle={len(changed)}; no performance delta emitted"
        )
    a, b = analyze(left), analyze(right)
    lines = [
        f"# Matched descriptive run comparison: {left.experiment.experiment_id}",
        "",
        (
            "All condition/case/repetition/seed keys, measured states and reference truths match. "
            "Changed predictions are allowed. Descriptive only; no IID or population inference."
        ),
        "",
        "| Quantity | Left | Right | Difference (right-left) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for field in ("tp", "fp", "tn", "fn", "detection_rows"):
        x, y = getattr(a.candidate, field), getattr(b.candidate, field)
        lines.append(f"| {field} | {x} | {y} | {y - x:+d} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m python_engineering.reporting")
    command = parser.add_subparsers(dest="command", required=True)
    for name in ("validate-run", "score-run"):
        p = command.add_parser(name)
        p.add_argument("input", type=Path)
        if name == "validate-run":
            p.add_argument("--evidence-root", type=Path)
    build = command.add_parser("build-report")
    build.add_argument("input", type=Path)
    build.add_argument("out", type=Path)
    build.add_argument("--evidence-root", type=Path)
    build.add_argument("--font", type=Path)
    comparison = command.add_parser("compare-runs")
    comparison.add_argument("left", type=Path)
    comparison.add_argument("right", type=Path)
    args = parser.parse_args(argv)
    if args.command == "validate-run":
        run = load_run(args.input)
        checks = _checks(run, args.evidence_root)
        print(
            f"VALID: {run.experiment.experiment_id}/{run.experiment.run_id} "
            f"sha256={_digest(args.input.read_bytes())}"
        )
        for check in checks:
            print(f"  {check.evidence_id}: {check.status.value}")
    elif args.command == "score-run":
        print(analyze(load_run(args.input)).model_dump_json(indent=2))
    elif args.command == "build-report":
        print(
            "BUILT: "
            + str(
                build_report(
                    args.input, args.out, evidence_root=args.evidence_root, font_path=args.font
                )
            )
        )
    else:
        print(compare_runs(load_run(args.left), load_run(args.right)), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
