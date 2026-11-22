"""Create *explicitly synthetic* fixtures; no empirical tool outcome is implied."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from python_engineering.reporting import REPORT_GENERATOR_VERSION
from python_engineering.reporting.models import (
    Condition,
    Criterion,
    Environment,
    EssentialGate,
    Evidence,
    EvidenceGrade,
    Experiment,
    Interpretation,
    Observation,
    ObservationState,
    Run,
    StudyStatus,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(("git", *args), text=True).strip()


def make_run(*, blocked: bool) -> Run:
    root = Path(__file__).resolve().parents[1]
    env = Environment(
        python_implementation=platform.python_implementation(),
        python_version=platform.python_version(),
        interpreter_executable=sys.executable,
        uv_version=subprocess.check_output(("uv", "--version"), text=True).strip(),
        os_name=platform.system(),
        os_release=platform.release(),
        architecture=platform.machine(),
        repository=git("remote", "get-url", "origin"),
        branch=git("branch", "--show-current"),
        commit_sha=git("rev-parse", "HEAD"),
        fixture_revision="synthetic-generator-v1",
        lockfile_sha256=sha256(root / "uv.lock"),
        pyproject_sha256=sha256(root / "pyproject.toml"),
        harness_version="synthetic-generator-v1",
        generator_version=REPORT_GENERATOR_VERSION,
        commands=(
            "uv run --locked python examples/build_demo_inputs.py",
            (
                "uv run --locked python -m python_engineering.reporting build-report "
                "examples/synthetic_900.json reports/E-900/synthetic-stress-v1"
            ),
        ),
        tool_versions={"SyntheticAnalyzer": "0.0.0-fictional"},
        dependency_versions={
            "pydantic": importlib.metadata.version("pydantic"),
            "reportlab": importlib.metadata.version("reportlab"),
        },
        runtime_identity=(
            "isolated macOS worktree; captured before publication; "
            "the Git source checkout may be dirty"
        ),
        hardware="NOT MEASURED",
        ci_runner="NOT APPLICABLE",
        random_seeds=(101,),
        source_retrieved_at=(
            "2026-11-17 (renderer documentation; exact retrieval timestamp unavailable)"
        ),
    )
    evidence = (
        Evidence(
            evidence_id="SYN-001",
            grade=EvidenceGrade.SYNTHETIC,
            source="examples/build_demo_inputs.py",
            locator="make_run / generated controlled pseudodata",
            source_sha256=sha256(Path(__file__)),
            note=(
                "Constructed synthetic rows are purposely not real analyzer observations. "
                "Long wrapped explanatory notes exercise PDF page and table layout and prevent "
                "a green-looking report from masquerading as independently verified evidence. "
                "Every result is synthetic and must be excluded from adoption decisions."
            ),
        ),
        Evidence(
            evidence_id="DOC-001",
            grade=EvidenceGrade.DOCUMENTATION,
            source="https://docs.reportlab.com/reportlab/userguide/ch7_tables/",
            locator="Tables and TableStyles / repeatRows",
            note=(
                "Official renderer capability documentation; "
                "not an observation or tool efficacy oracle."
            ),
        ),
    )
    anchors_precision = (
        "precision < 0.50",
        "0.50 to < 0.70",
        "0.70 to < 0.85",
        "0.85 to < 0.95",
        "precision >= 0.95 (requires independent corroboration to qualify)",
    )
    anchors_duration = (
        "median > 80ms",
        "40 < median <= 80ms",
        "20 < median <= 40ms",
        "10 < median <= 20ms",
        "median <= 10ms; no correctness substitution",
    )
    criteria = (
        Criterion(
            criterion_id="C-precision",
            category="static_typing",
            dimension="false_positive_burden",
            question="What fraction of flagged cases have seeded defects?",
            metric="precision",
            condition_id="candidate",
            direction="higher",
            thresholds=(0.50, 0.70, 0.85, 0.95),
            anchors=anchors_precision,
            min_denominator=10,
        ),
        Criterion(
            criterion_id="C-duration",
            category="static_typing",
            dimension="performance",
            question="What is the candidate median execution time in ms?",
            metric="median_duration_ms",
            condition_id="candidate",
            direction="lower",
            thresholds=(10.0, 20.0, 40.0, 80.0),
            anchors=anchors_duration,
            min_denominator=10,
        ),
    )
    observations: tuple[Observation, ...] = ()
    if blocked:
        observations = (
            Observation(
                observation_id="blocked-001",
                condition_id="candidate",
                case_id="unexecuted_case_001",
                state=ObservationState.BLOCKED,
                evidence_id="SYN-001",
                note="No actual invocation or outcome exists",
            ),
        )
    else:
        items = []
        for i in range(1, 66):
            expected = i % 3 == 0
            for condition in ("baseline", "candidate"):
                detected = (expected and i % (5 if condition == "baseline" else 7) != 0) or (
                    not expected and i % (17 if condition == "baseline" else 29) == 0
                )
                items.append(
                    Observation(
                        observation_id=f"synthetic-{i:03}-{condition}",
                        condition_id=condition,
                        case_id=f"synthetic_case_{i:03}",
                        state=ObservationState.MEASURED,
                        evidence_id="SYN-001",
                        repetition=0,
                        seed=101,
                        expected_defect=expected,
                        detected_defect=detected,
                        duration_ms=float((7 if condition == "baseline" else 5) + (i % 13)),
                        note="SIMULATED AND NOT EMPIRICAL",
                    )
                )
        observations = tuple(items)
    tag = "synthetic-blocked-v1" if blocked else "synthetic-stress-v1"
    return Run(
        schema_version="1.0",
        rubric_revision="synthetic-demo-rubric-v1",
        experiment=Experiment(
            experiment_id="E-901" if blocked else "E-900",
            protocol_revision="SYNTHETIC-NOT-REGISTERED-v1",
            title=(
                "Synthetic reporting abstention demonstration"
                if blocked
                else "Synthetic analyzer comparison and table-stress demonstration"
            ),
            run_id=tag,
            executed_at=datetime.now(UTC),
            status=StudyStatus.BLOCKED if blocked else StudyStatus.PILOT,
            research_question=(
                "Can the reporting harness preserve synthetic evidence labels and uncertainty?"
            ),
            hypothesis=(
                "Unknown results remain unscored and synthetic measurements never imply efficacy."
            ),
            prespecified_criteria=(
                "Check validation, tables, evidence-grade, score threshold boundaries and gates."
            ),
        ),
        environment=env,
        baseline=Condition(
            condition_id="baseline",
            upstream_identity="FictionalAnalyzer",
            version="0.0.0",
            configuration="synthetic test default",
        ),
        candidate=Condition(
            condition_id="candidate",
            upstream_identity="FictionalAnalyzer",
            version="0.0.0-fictional",
            configuration="synthetic aggressive flags",
        ),
        observations=observations,
        evidence=evidence,
        criteria=criteria,
        gates=(
            EssentialGate(
                gate_id="G-independent",
                requirement="Independent replication",
                passed=None,
                note="No independent or real experimental evidence",
            ),
            EssentialGate(
                gate_id="G-repro",
                requirement="Real tool invocation reproduced",
                passed=False if blocked else None,
                note="Simulation does not run a real upstream tool",
            ),
        ),
        interpretation=Interpretation(
            summary="Artificial run used exclusively to verify the reporting implementation.",
            limitations=(
                "All observed numbers and defect labels are generated, not tool measurements.",
                (
                    "Repeated or paired rows are synthetic; "
                    "no generalization or statistical inference."
                ),
                "Upstream identity is intentionally fictional and nonqualified.",
            ),
            applicability=(
                "PDF/Markdown renderer, validation, page flow, "
                "missing evidence and score mechanics only"
            ),
            reviewer="Automated synthetic fixture generator (not independent)",
            disposition="NO ADOPTION DECISION - SYNTHETIC DEMO",
            proposed_next_step=(
                "Independent review and real frozen protocol-scoped experimental run."
            ),
        ),
        synthetic_demonstration=True,
    )


if __name__ == "__main__":
    directory = Path(__file__).resolve().parent
    for blocked in (False, True):
        run = make_run(blocked=blocked)
        path = directory / ("synthetic_901.json" if blocked else "synthetic_900.json")
        path.write_text(run.model_dump_json(indent=2) + "\n")
        print(path)
