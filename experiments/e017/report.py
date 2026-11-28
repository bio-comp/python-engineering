"""Project local E-017 evidence into the existing reporting contract.

The report is case-level acceptance evidence, not a substitute for the
dependency-level verdicts or a proof of externally attested execution.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from experiments.e017.oracle import (
    Receipt,
    State,
    Verdict,
    digest,
    extraction_control_correct,
    judge_logs,
    load_fixtures,
    policy_control_correct,
)
from experiments.e017.run import HERE, source_identity
from python_engineering.reporting import REPORT_GENERATOR_VERSION
from python_engineering.reporting.cli import build_report
from python_engineering.reporting.models import (
    SHA256,
    Condition,
    Contract,
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


class UpdateVerdict(Contract):
    state: State
    diagnostics: tuple[str, ...]
    after: dict[str, SHA256]
    repeated: dict[str, SHA256] | None = None
    expected_state: Literal["FAIL"] | None = None
    control_correct: bool | None = None
    raw_manifest_mutated: bool | None = None


class PolicyVerdict(Contract):
    command: tuple[str, ...]
    environment: dict[str, str]
    expected_valid: bool
    returncode: int
    stdout_sha256: SHA256
    stderr_sha256: SHA256
    config_sha256: SHA256
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    control_correct: bool
    scope: str


def make_run(
    root: Path,
    extract: Path,
    lookup: Path,
    updates: Path,
    run_id: str,
) -> Run:
    repo = HERE.parents[1]
    identity = source_identity()
    sha = str(identity["source_commit"])
    if identity["source_dirty"]:
        raise ValueError("report requires the exact clean experiment source")
    for directory, name in (
        (extract, "run-identity.json"),
        (lookup, "run-identity.json"),
        (updates, "identity.json"),
    ):
        recorded = json.loads((directory / name).read_bytes())
        if (
            recorded["source_commit"] != sha
            or recorded["source_dirty"]
            or recorded["source_files"] != identity["source_files"]
            or recorded["lockfile_sha256"] != identity["lockfile_sha256"]
            or recorded["pyproject_sha256"] != identity["pyproject_sha256"]
        ):
            raise ValueError("run source identity mismatch")
    evidence: list[Evidence] = []
    observations: list[Observation] = []
    gates: list[EssentialGate] = []

    def register(path: Path, note: str) -> str:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("evidence outside authorized root")
        key = f"evidence-{len(evidence) + 1}"
        evidence.append(
            Evidence(
                evidence_id=key,
                grade=EvidenceGrade.CONTROLLED,
                source=path.relative_to(root).as_posix(),
                locator=path.name,
                source_sha256=digest(path.read_bytes()),
                note=note,
            )
        )
        return key

    fixture_cases = load_fixtures(HERE / "corpus.json")
    extraction_ok = True
    refs = []
    for case in fixture_cases:
        verdicts = []
        for rep in (1, 2):
            path = extract / f"{case.case_id}-extract-{rep}"
            rec = Receipt.model_validate_json((path / "receipt.json").read_bytes())
            verdict = judge_logs(
                case,
                "extract",
                rec,
                (path / "stdout.jsonl").read_bytes(),
                (path / "stderr.txt").read_bytes(),
            )
            saved = Verdict.model_validate_json((path / "verdict.json").read_bytes())
            if verdict != saved:
                raise ValueError("saved extraction verdict differs from replay")
            verdicts.append(verdict)
            refs.append(register(path / "verdict.json", "Recomputed extraction case verdict."))
            extraction_ok = extraction_ok and extraction_control_correct(verdict)
        extraction_ok = extraction_ok and verdicts[0] == verdicts[1]
    gates.append(
        EssentialGate(
            gate_id="extraction",
            requirement="Exact scoped extraction and replay",
            passed=extraction_ok,
            evidence_ids=tuple(refs),
            note="Dependency-category counts are retained in each verdict JSON.",
        )
    )
    path = lookup / "mixed-extraction-lookup-1"
    rec = Receipt.model_validate_json((path / "receipt.json").read_bytes())
    verdict = judge_logs(
        fixture_cases[0],
        "lookup",
        rec,
        (path / "stdout.jsonl").read_bytes(),
        (path / "stderr.txt").read_bytes(),
    )
    if verdict != Verdict.model_validate_json((path / "verdict.json").read_bytes()):
        raise ValueError("saved lookup verdict differs from replay")
    gates.append(
        EssentialGate(
            gate_id="lookup",
            requirement="Complete critical lookup evidence",
            passed=verdict.state == State.PASS,
            evidence_ids=(register(path / "verdict.json", "Live lookup replay."),),
            note="Release availability not independently frozen.",
        )
    )
    refs = []
    policy_ok = True
    for name in ("repository", "administrative", "obsolete", "invalid-manager", "invalid-type"):
        path = extract / f"policy-{name}"
        rec_policy = PolicyVerdict.model_validate_json((path / "receipt.json").read_bytes())
        if (
            rec_policy.stdout_sha256 != digest((path / "stdout.jsonl").read_bytes())
            or rec_policy.stderr_sha256 != digest((path / "stderr.txt").read_bytes())
            or rec_policy.config_sha256 != digest((path / "candidate.json").read_bytes())
        ):
            raise ValueError("configuration receipt digest mismatch")
        refs.append(register(path / "receipt.json", "Exact-version schema validator receipt."))
        config = json.loads((HERE / "policies.json").read_bytes())[name]
        if json.loads((path / "candidate.json").read_bytes()) != config:
            raise ValueError("policy fixture mismatch")
        computed = policy_control_correct(
            name,
            (path / "candidate.json").read_bytes(),
            (path / "stdout.jsonl").read_bytes(),
            (path / "stderr.txt").read_bytes(),
            rec_policy.returncode,
        )
        if computed != rec_policy.control_correct:
            raise ValueError("saved policy verdict differs from replay")
        policy_ok = policy_ok and computed
    gates.append(
        EssentialGate(
            gate_id="configuration",
            requirement="Strict schema controls",
            passed=policy_ok,
            evidence_ids=tuple(refs),
            note="Not operational policy enforcement.",
        )
    )
    update_ok = True
    refs = []
    arms: tuple[tuple[str, Literal["baseline", "candidate"]], ...] = (
        ("native-uv", "baseline"),
        ("renovate", "candidate"),
    )
    for update_case, rep in (
        ("requests-regression", 1),
        ("requests-regression", 2),
        ("idna-independent", 1),
        ("idna-independent", 2),
        ("requests-regression", 3),
    ):
        conflict = rep == 3
        case_id = "requests-conflict" if conflict else update_case
        pairs = []
        for arm, condition in arms:
            path = updates / f"{update_case}-{arm}-{rep}"
            result = UpdateVerdict.model_validate_json((path / "verdict.json").read_bytes())
            expected = State.FAIL if conflict else State.PASS
            valid = result.state == expected and (not conflict or result.control_correct is True)
            update_ok = update_ok and valid
            refs.append(register(path / "verdict.json", "Runner-recorded update/lock acceptance."))
            pairs.append(result.after)
            measured = result.state in (State.PASS, State.FAIL)
            observations.append(
                Observation(
                    observation_id=f"{case_id}-{condition}-{rep}",
                    condition_id=condition,
                    case_id=case_id,
                    repetition=rep,
                    state=ObservationState.MEASURED if measured else ObservationState.BLOCKED,
                    evidence_id=refs[-1],
                    expected_defect=conflict if measured else None,
                    detected_defect=result.state == State.FAIL if measured else None,
                    note="; ".join(result.diagnostics) or "Expected manifest/lock result accepted.",
                )
            )
        if not conflict:
            update_ok = update_ok and pairs[0] == pairs[1]
    gates.append(
        EssentialGate(
            gate_id="updates",
            requirement="Matched targeted update controls",
            passed=update_ok,
            evidence_ids=tuple(refs),
            note="Source-declared runner verdicts; not independent replication.",
        )
    )
    for key, requirement in (
        ("oci", "Official OCI distribution"),
        ("dependabot", "Genuine isolated Dependabot comparison"),
        ("release-oracle", "Frozen external release availability"),
        ("policy-enforcement", "Operational policy enforcement"),
    ):
        gates.append(
            EssentialGate(
                gate_id=key,
                requirement=requirement,
                passed=None,
                note="Not executed or not established in this condition.",
            )
        )
    return Run(
        schema_version="1.0",
        rubric_revision="e017-q1-case-acceptance-v1",
        experiment=Experiment(
            experiment_id="E-017",
            protocol_revision="Q1-local-v1",
            title="Renovate Q1 local evidence",
            run_id=run_id,
            executed_at=datetime.now(UTC),
            status=StudyStatus.INCOMPLETE,
            research_question="Can scoped dependency operations avoid false green?",
            hypothesis="Correct operations and conflicting requirements are distinguishable.",
            prespecified_criteria="Exact manifests, locks, repeatability and fail-closed results.",
        ),
        environment=Environment(
            python_implementation=platform.python_implementation(),
            python_version=platform.python_version(),
            interpreter_executable=sys.executable,
            uv_version="0.13.9",
            os_name=platform.system(),
            os_release=platform.release(),
            architecture=platform.machine(),
            repository="bio-comp/python-engineering",
            branch="feat/issue21-renovate-q1",
            commit_sha=sha,
            fixture_revision=digest((HERE / "corpus.json").read_bytes()),
            lockfile_sha256=digest((repo / "uv.lock").read_bytes()),
            pyproject_sha256=digest((repo / "pyproject.toml").read_bytes()),
            harness_version="e017-q1-v1",
            generator_version=REPORT_GENERATOR_VERSION,
            commands=(
                "python -m experiments.e017.run --stage extract --policies",
                "python -m experiments.e017.run --stage lookup",
                "python -m experiments.e017.updates",
                "python -m experiments.e017.report",
            ),
            tool_versions={
                "Renovate": "45.3.2 npm RE2 fallback",
                "Node": "26.13.1",
                "uv": "0.13.9",
            },
            dependency_versions={"pydantic": importlib.metadata.version("pydantic")},
            runtime_identity="isolated Linux npm component/local CLI; live public index",
        ),
        baseline=Condition(
            condition_id="baseline",
            upstream_identity="astral-sh/uv",
            version="0.13.9",
            configuration="exact targeted native lock update",
        ),
        candidate=Condition(
            condition_id="candidate",
            upstream_identity="renovatebot/renovate",
            version="45.3.2",
            configuration="npm internal PEP 621 component",
        ),
        observations=tuple(observations),
        evidence=tuple(evidence),
        criteria=(),
        gates=tuple(gates),
        interpretation=Interpretation(
            summary="Local case-level acceptance and explicit unqualified conditions.",
            limitations=(
                "Not independent replication or production readiness.",
                "Case-level defect rows describe conflicting requirements, not dependency counts.",
                "No frozen release index, authenticated PR, OCI or Dependabot run.",
                "Conflict leaves staging manifest modified; no rollback claim.",
            ),
            applicability="Frozen cases; exact observed npm and native uv conditions only.",
            reviewer="UNREVIEWED local implementation",
            disposition="INCOMPLETE; no practice promotion",
            proposed_next_step="Independent review; close blocked arms before operational Q2.",
        ),
        synthetic_demonstration=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--extract", type=Path, required=True)
    parser.add_argument("--lookup", type=Path, required=True)
    parser.add_argument("--updates", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    out = args.out.resolve()
    run = make_run(
        root,
        args.extract.resolve(strict=True),
        args.lookup.resolve(strict=True),
        args.updates.resolve(strict=True),
        out.name,
    )
    input_path = out.with_suffix(".input.json")
    with input_path.open("xb") as f:
        f.write(run.model_dump_json(indent=2).encode())
    print(build_report(input_path, out, evidence_root=root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
