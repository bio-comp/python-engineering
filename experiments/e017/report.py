"""Project local E-017 evidence into the existing reporting contract.

The report is case-level acceptance evidence, not a substitute for the
dependency-level verdicts or a proof of externally attested execution.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from experiments.e017.evidence import (
    Arm,
    BoundExtraction,
    EvidenceError,
    PolicyReceipt,
    ProcessReceipt,
    RunIdentity,
    RunStage,
    bind_extraction,
    bind_process,
    expected_environment,
    log_context,
    ordered,
    read_bytes,
    read_model,
    require,
)
from experiments.e017.oracle import (
    State,
    Verdict,
    digest,
    extraction_control_correct,
    judge_logs,
    material_context,
    policy_control_correct,
)
from experiments.e017.run import HERE, corpus, fixture_identity, snapshot, source_identity
from experiments.e017.updates import checked_tree, replay_update, specs
from python_engineering.reporting import REPORT_GENERATOR_VERSION
from python_engineering.reporting.cli import build_report
from python_engineering.reporting.models import (
    Condition,
    Environment,
    EssentialGate,
    Evidence,
    EvidenceGrade,
    Experiment,
    Interpretation,
    Observation,
    ObservationState,
    ReplayManifest,
    Run,
    StudyStatus,
)


def verify_population(root: Path, expected: set[str], optional: set[str]) -> None:
    if not root.is_dir():
        raise EvidenceError(State.BLOCKED, "missing stage evidence directory")
    require(not root.is_symlink(), "symlinked stage directory")
    found = {item.name for item in root.iterdir() if item.is_dir()}
    if expected - found:
        raise EvidenceError(State.BLOCKED, "missing required case population")
    require(not found - expected - optional, "unexpected case population")


def make_run(
    root: Path,
    extract: Path,
    lookup: Path,
    updates: Path,
    run_id: str,
    *,
    allow_synthetic: bool = False,
) -> Run:
    """Reject incomplete or inconsistent evidence before producing a report."""
    try:
        return _make_run(root, extract, lookup, updates, run_id, allow_synthetic=allow_synthetic)
    except EvidenceError:
        raise
    except FileNotFoundError as exc:
        raise EvidenceError(State.BLOCKED, "missing required artifact") from exc
    except (ValueError, OSError) as exc:
        raise EvidenceError(State.FAIL, str(exc)) from exc


def _make_run(
    root: Path,
    extract: Path,
    lookup: Path,
    updates: Path,
    run_id: str,
    *,
    allow_synthetic: bool,
) -> Run:
    repo = HERE.parents[1]
    source = source_identity()
    stage_paths: tuple[tuple[RunStage, Path, str], ...] = (
        ("extract", extract, "run-identity.json"),
        ("lookup", lookup, "run-identity.json"),
        ("updates", updates, "identity.json"),
    )
    identities = {}
    for stage, directory, filename in stage_paths:
        require(
            directory.resolve().is_relative_to(root.resolve()),
            "stage evidence outside authorized root",
        )
        identity = read_model(directory / filename, RunIdentity)
        require(
            identity.stage == stage and identity.source == source,
            "run source/stage identity mismatch",
        )
        require(identity.fixture_sha256 == fixture_identity(), "run fixture identity mismatch")
        require(
            identity.distribution != "synthetic-control" or allow_synthetic,
            "synthetic evidence cannot support genuine execution",
        )
        require(
            identity.distribution == "synthetic-control" or not source.source_dirty,
            "real report requires exact clean source",
        )
        identities[stage] = identity
    extraction_identity = identities["extract"]
    # Stage roots and capture timestamps differ; every other material condition
    # must match, including exact executable and distribution identities.
    for identity in identities.values():
        require(
            identity.model_dump(exclude={"stage", "execution_root", "executed_at"})
            == extraction_identity.model_dump(exclude={"stage", "execution_root", "executed_at"}),
            "inconsistent comparator/run identities",
        )
    require(
        len({identity.execution_root for identity in identities.values()}) == 3,
        "duplicate execution stage roots",
    )
    require(
        len({Path(identity.execution_root).parent for identity in identities.values()}) == 1,
        "mixed experiment bundles",
    )
    synthetic = extraction_identity.distribution == "synthetic-control"
    sha = source.source_commit
    fixture_cases = corpus()
    policy_names = ("repository", "administrative", "obsolete", "invalid-manager", "invalid-type")
    update_specs = specs()
    repetitions: tuple[Literal[1, 2], ...] = (1, 2)
    update_cases: tuple[tuple[str, Literal[1, 2, 3]], ...] = (
        *((spec.case_id, rep) for spec in update_specs for rep in repetitions),
        (update_specs[0].case_id, 3),
    )
    verify_population(
        extract,
        {f"{case.case_id}-extract-{rep}" for case in fixture_cases for rep in (1, 2)}
        | {f"policy-{name}" for name in policy_names},
        {"identity-probe", "expected-inputs"},
    )
    verify_population(lookup, {"mixed-extraction-lookup-1"}, {"identity-probe"})
    verify_population(
        updates,
        {f"{case}-{arm}-{rep}" for case, rep in update_cases for arm in ("native-uv", "renovate")},
        {"identity-probe", "shared-uv-cache"},
    )
    require(
        snapshot(extract / "expected-inputs") == extraction_identity.fixture_sha256,
        "retained expected input population mismatch",
    )
    members: dict[str, str] = {}

    def retain(path: Path) -> None:
        require(path.resolve().is_relative_to(root), "replay artifact outside evidence root")
        members[path.relative_to(root).as_posix()] = digest(read_bytes(path))

    def retain_tree(path: Path) -> None:
        for name in checked_tree(path):
            retain(path / name)

    def retain_extraction(path: Path) -> None:
        for name in ("receipt.json", "stdout.jsonl", "stderr.txt", "verdict.json"):
            retain(path / name)
        retain_tree(path / "fixture")

    for _, directory, filename in stage_paths:
        retain(directory / filename)
    retain_tree(extract / "expected-inputs")
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
                grade=EvidenceGrade.SYNTHETIC if synthetic else EvidenceGrade.CONTROLLED,
                source=path.relative_to(root).as_posix(),
                locator=path.name,
                source_sha256=digest(read_bytes(path)),
                note=note,
            )
        )
        return key

    extraction_ok = True
    previous = extraction_identity.executed_at
    refs = [register(extract / "run-identity.json", "Versioned extraction condition identity.")]
    for case in fixture_cases:
        verdicts = []
        for rep in (1, 2):
            path = extract / f"{case.case_id}-extract-{rep}"
            rec = read_model(path / "receipt.json", BoundExtraction)
            bind_extraction(extraction_identity, rec, case.case_id, rep, case.fingerprint())
            ordered(previous, rec.started_at, "overlapping or reversed extraction cases")
            previous = rec.executed_at
            material_context(
                read_bytes(path / "stdout.jsonl"),
                "extract",
                context=log_context(extraction_identity, extraction_identity.case_path(path.name)),
                started_at=rec.started_at,
                completed_at=rec.executed_at,
            )
            retain_extraction(path)
            require(snapshot(path / "fixture") == rec.after, "extraction retained bytes mismatch")
            verdict = judge_logs(
                case,
                "extract",
                rec,
                read_bytes(path / "stdout.jsonl"),
                read_bytes(path / "stderr.txt"),
            )
            saved = read_model(path / "verdict.json", Verdict)
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
    rec = read_model(path / "receipt.json", BoundExtraction)
    bind_extraction(
        identities["lookup"], rec, fixture_cases[0].case_id, 1, fixture_cases[0].fingerprint()
    )
    material_context(
        read_bytes(path / "stdout.jsonl"),
        "lookup",
        context=log_context(identities["lookup"], identities["lookup"].case_path(path.name)),
        started_at=rec.started_at,
        completed_at=rec.executed_at,
    )
    retain_extraction(path)
    lookup_completion = rec.executed_at
    require(snapshot(path / "fixture") == rec.after, "lookup retained bytes mismatch")
    verdict = judge_logs(
        fixture_cases[0],
        "lookup",
        rec,
        read_bytes(path / "stdout.jsonl"),
        read_bytes(path / "stderr.txt"),
    )
    if verdict != read_model(path / "verdict.json", Verdict):
        raise ValueError("saved lookup verdict differs from replay")
    gates.append(
        EssentialGate(
            gate_id="lookup",
            requirement="Complete critical lookup evidence",
            passed=verdict.state == State.PASS,
            evidence_ids=(
                register(path / "verdict.json", "Live lookup replay."),
                register(lookup / "run-identity.json", "Versioned lookup identity."),
            ),
            note="Release availability not independently frozen.",
        )
    )
    refs = []
    policy_ok = True
    for name in policy_names:
        path = extract / f"policy-{name}"
        rec_policy = read_model(path / "receipt.json", PolicyReceipt)
        ordered(previous, rec_policy.started_at, "overlapping or reversed policy cases")
        previous = rec_policy.executed_at
        for name_of_file in ("receipt.json", "candidate.json", "stdout.jsonl", "stderr.txt"):
            retain(path / name_of_file)
        config = json.loads((HERE / "policies.json").read_bytes())[name]
        candidate = read_bytes(path / "candidate.json")
        require(candidate == json.dumps(config, indent=2).encode(), "policy fixture mismatch")
        candidate_sha = digest(candidate)
        require(
            rec_policy.config_sha256 == candidate_sha
            and rec_policy.expected_valid == (name in {"repository", "administrative"}),
            "policy identity/expected validity mismatch",
        )
        case_path = extraction_identity.case_path(f"policy-{name}")
        command: tuple[str, ...] = (
            extraction_identity.node.path,
            extraction_identity.validator.path,
            "--strict",
        )
        if name != "administrative":
            command += ("--no-global",)
        command += (str(case_path / "candidate.json"),)
        stdout, stderr = read_bytes(path / "stdout.jsonl"), read_bytes(path / "stderr.txt")
        bind_process(
            extraction_identity,
            rec_policy,
            case_id=name,
            repetition=1,
            arm="renovate",
            operation="policy",
            fixture_sha=candidate_sha,
            command=command,
            cwd=case_path,
            env=expected_environment(extraction_identity, case_path),
            stdout=stdout,
            stderr=stderr,
        )
        refs.append(register(path / "receipt.json", "Exact-version schema validator receipt."))
        computed = policy_control_correct(
            name,
            candidate,
            stdout,
            stderr,
            rec_policy.returncode,
            distribution=extraction_identity.distribution,
        )
        require(computed == rec_policy.control_correct, "saved policy verdict differs from replay")
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
    ordered(
        previous, identities["lookup"].executed_at, "lookup stage starts before extraction ends"
    )
    ordered(
        lookup_completion, identities["updates"].executed_at, "updates start before lookup ends"
    )
    previous = identities["updates"].executed_at
    update_ok = True
    refs = [register(updates / "identity.json", "Versioned update identity.")]
    arms: tuple[tuple[Arm, Literal["baseline", "candidate"]], ...] = (
        ("renovate", "candidate"),
        ("native-uv", "baseline"),
    )
    outputs: dict[str, list[dict[str, bytes]]] = {}
    for update_case, rep in update_cases:
        conflict = rep == 3
        case_id = "requests-conflict" if conflict else update_case
        spec = next(spec for spec in update_specs if spec.case_id == update_case)
        for arm, condition in arms:
            path = updates / f"{update_case}-{arm}-{rep}"
            result, actual = replay_update(identities["updates"], spec, arm, rep, updates)
            first = read_model(path / "initial-check.json", ProcessReceipt)
            last = read_model(path / ("update.json" if conflict else "repeat.json"), ProcessReceipt)
            ordered(previous, first.started_at, "overlapping or reversed update cases")
            previous = last.executed_at
            for file in (
                "initial.json",
                "generated.json",
                "verdict.json",
                "uv-invocations.jsonl",
                "bin/uv",
            ):
                retain(path / file)
            for snapshot_name in ("initial", "generated", "fixture"):
                retain_tree(path / snapshot_name)
            if not conflict:
                retain(path / "repeated.json")
                retain_tree(path / "repeated")
            phases = (
                ("initial-check", "update")
                if conflict
                else ("initial-check", "update", "lock-check", "repeat")
            )
            for index, phase in enumerate(phases, 1):
                for suffix in ("json", "stdout", "stderr"):
                    retain(path / f"{phase}.{suffix}")
                attempt = path / "uv-attempts" / str(index)
                for file in ("receipt.json", "stdout", "stderr"):
                    retain(attempt / file)
                for snapshot_name in ("before", "after"):
                    retain_tree(attempt / snapshot_name)
            expected = State.FAIL if conflict else State.PASS
            valid = result.state == expected and (not conflict or result.control_correct is True)
            update_ok = update_ok and valid
            refs.append(
                register(path / "verdict.json", "Update verdict reconstructed from retained bytes.")
            )
            if not conflict:
                outputs.setdefault(update_case, []).append(actual)
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
    for results in outputs.values():
        update_ok = update_ok and len(results) == 4 and all(x == results[0] for x in results)
    gates.append(
        EssentialGate(
            gate_id="updates",
            requirement="Matched targeted update controls",
            passed=update_ok,
            evidence_ids=tuple(refs),
            note="Replayed raw receipts and byte snapshots; matched across both repetitions.",
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
    anchor = (extract / "run-identity.json").relative_to(root).as_posix()
    manifest_id = "replay-population-v1"
    evidence.append(
        Evidence(
            evidence_id=manifest_id,
            grade=EvidenceGrade.SYNTHETIC if synthetic else EvidenceGrade.CONTROLLED,
            source=anchor,
            source_sha256=members[anchor],
            locator="embedded replay manifest v1",
            note=f"All {len(members)} required replay artifacts; byte integrity, not attestation.",
            replay_manifest=ReplayManifest(members=members),
        )
    )
    gates = [
        gate.model_copy(update={"evidence_ids": (*gate.evidence_ids, manifest_id)})
        if gate.passed is not None
        else gate
        for gate in gates
    ]
    return Run(
        schema_version="1.0",
        rubric_revision="e017-q1-case-acceptance-v3",
        experiment=Experiment(
            experiment_id="E-017",
            protocol_revision="Q1-local-r2-v3",
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
            python_version=extraction_identity.python.version,
            interpreter_executable=extraction_identity.python.path,
            uv_version="0.13.9",
            os_name=platform.system(),
            os_release=platform.release(),
            architecture=platform.machine(),
            repository="bio-comp/python-engineering",
            branch="feat/issue21-renovate-q1",
            commit_sha=sha,
            fixture_revision=digest(json.dumps(fixture_identity(), sort_keys=True).encode()),
            lockfile_sha256=digest((repo / "uv.lock").read_bytes()),
            pyproject_sha256=digest((repo / "pyproject.toml").read_bytes()),
            harness_version="e017-q1-r2-v3",
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
                "Replay verification checks retained bytes, not independent runtime attestation.",
                "Case-level defect rows describe conflicting requirements, not dependency counts.",
                "No frozen release index, authenticated PR, OCI or Dependabot run.",
                "Conflict leaves staging manifest modified; no rollback claim.",
            ),
            applicability="Frozen cases; exact observed npm and native uv conditions only.",
            reviewer="UNREVIEWED local implementation",
            disposition="INCOMPLETE; no practice promotion",
            proposed_next_step="Independent review; close blocked arms before operational Q2.",
        ),
        synthetic_demonstration=synthetic,
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
