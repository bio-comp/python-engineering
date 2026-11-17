"""A bounded no-agent/no-network smoke test, never a scored effectiveness trial."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from python_engineering.e010.contracts import (
    RetrievalBudget,
    RetrievalCondition,
    TaskSpec,
    TrialRecord,
)
from python_engineering.e010.provenance import capture_unrun_manifest, write_new_record
from python_engineering.e010.scoring import score_observations


def run_demo(project_root: Path) -> dict[str, bool | int | str]:
    root = project_root / "experiments" / "e010"
    case = root / "fixtures" / "published_test"
    task = TaskSpec.model_validate_json((case / "task.json").read_bytes())
    fixture = case / "inputs.json"
    oracle = root / "oracles" / "stdlib_trim.json"
    with TemporaryDirectory() as temp:
        solver = Path(temp)
        good = solver / "good.json"
        bad = solver / "bad.json"
        good.write_bytes((case / "observed_valid.json").read_bytes())
        bad.write_bytes((case / "observed_bad.json").read_bytes())
        valid = score_observations(
            task=task,
            fixture_file=fixture,
            oracle_file=oracle,
            trace_file=good,
            solver_workspace=solver,
        )
        invalid = score_observations(
            task=task,
            fixture_file=fixture,
            oracle_file=oracle,
            trace_file=bad,
            solver_workspace=solver,
        )
    return {
        "scope": "offline_synthetic_observation_consistency_only",
        "valid_observation_passed": valid.passed,
        "known_bad_observation_rejected": not invalid.passed,
        "cases_assessed": valid.assessed_cases,
        "agent_trials_run": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        help="New empty output directory for four explicitly NOT-RUN manifests",
    )
    args = parser.parse_args()
    project_root = Path.cwd()
    result = run_demo(project_root)
    if args.manifest_dir is not None:
        args.manifest_dir.mkdir(parents=False, exist_ok=False)
        task_file = (
            project_root / "experiments" / "e010" / "fixtures" / "published_test" / "task.json"
        )
        task = TaskSpec.model_validate_json(task_file.read_bytes())
        for condition in RetrievalCondition:
            manifest = capture_unrun_manifest(
                task=task,
                condition=condition,
                budget=RetrievalBudget.BALANCED,
                project_root=project_root,
                seed=101,
            )
            record = TrialRecord(
                manifest=manifest,
                status="not_run",
                correctness=None,
                invalid_reason=None,
            )
            digest = write_new_record(
                args.manifest_dir / f"condition-{condition.value}-not-run.json", record
            )
            result[f"condition_{condition.value}_record_sha256"] = digest
        result["not_run_manifest_count"] = 4
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
