"""Artifact CLI: validate, score, build and compare without rewriting raw observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from python_engineering.reporting import REPORT_GENERATOR_VERSION
from python_engineering.reporting.analysis import analyze
from python_engineering.reporting.models import Run
from python_engineering.reporting.render import render_markdown, render_pdf


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_run(path: Path) -> Run:
    """Pydantic parses JSON directly; no lossy intermediate source transformation."""
    return Run.model_validate_json(path.read_bytes())


def _write_new(path: Path, contents: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(contents)


def build_report(source: Path, target_dir: Path) -> Path:
    """Exclusive directory creation prevents rewriting purported immutable run artifacts."""
    original = source.read_bytes()
    run = Run.model_validate_json(original)
    result = analyze(run)
    target_dir.mkdir(parents=True, exist_ok=False)
    payloads = {
        "run.json": original,
        "analysis.json": (result.model_dump_json(indent=2) + "\n").encode(),
        "summary.md": render_markdown(run, result, detailed=False).encode(),
        "report.md": render_markdown(run, result, detailed=True).encode(),
    }
    for name, data in payloads.items():
        _write_new(target_dir / name, data)
    pdf_path = target_dir / "report.pdf"
    render_pdf(run, result, pdf_path)
    artifacts = sorted(
        (name, _digest((target_dir / name).read_bytes())) for name in (*payloads, "report.pdf")
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
        "files_sha256": dict(artifacts),
    }
    _write_new(
        target_dir / "manifest.json",
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
    )
    return target_dir / "manifest.json"


def compare_runs(left: Run, right: Run) -> str:
    """Reject cross-study ranking or changed protocol/conditions as incommensurable."""
    if (
        left.experiment.experiment_id != right.experiment.experiment_id
        or left.experiment.protocol_revision != right.experiment.protocol_revision
        or left.baseline != right.baseline
        or left.candidate != right.candidate
        or left.rubric_revision != right.rubric_revision
        or left.criteria != right.criteria
    ):
        raise ValueError("incomparable experiment/protocol/conditions/rubric; no automatic ranking")
    a, b = analyze(left), analyze(right)
    lines = [
        f"# Comparable run snapshots: {left.experiment.experiment_id}",
        "",
        (
            "Descriptive differences only; changed fixtures/sample populations "
            "need separate qualification."
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
    build = command.add_parser("build-report")
    build.add_argument("input", type=Path)
    build.add_argument("out", type=Path)
    comparison = command.add_parser("compare-runs")
    comparison.add_argument("left", type=Path)
    comparison.add_argument("right", type=Path)
    args = parser.parse_args(argv)
    if args.command == "validate-run":
        run = load_run(args.input)
        print(
            f"VALID: {run.experiment.experiment_id}/{run.experiment.run_id} "
            f"sha256={_digest(args.input.read_bytes())}"
        )
    elif args.command == "score-run":
        print(analyze(load_run(args.input)).model_dump_json(indent=2))
    elif args.command == "build-report":
        print(f"BUILT: {build_report(args.input, args.out)}")
    else:
        print(compare_runs(load_run(args.left), load_run(args.right)), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
