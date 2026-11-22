"""Independent-review counterexamples for E-010's offline trust boundaries."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from python_engineering.e010.contracts import (
    OfflineScore,
    RetrievalBudget,
    RetrievalCondition,
    TaskSpec,
)
from python_engineering.e010.provenance import capture_unrun_manifest
from python_engineering.e010.scoring import IntegrityError, score_observations

ROOT = Path(__file__).resolve().parents[2]
E010 = ROOT / "experiments" / "e010"
CALIBRATION = E010 / "fixtures" / "calibration"
PUBLISHED = E010 / "fixtures" / "published_test"


def calibration_task() -> TaskSpec:
    return TaskSpec.model_validate_json((CALIBRATION / "task.json").read_bytes())


def published_task() -> TaskSpec:
    return TaskSpec.model_validate_json((PUBLISHED / "task.json").read_bytes())


def synthetic_case_files(
    root: Path,
    *,
    fixture_ids: tuple[str, ...] = ("a", "b"),
    oracle_ids: tuple[str, ...] = ("a", "b"),
    observed_ids: tuple[str, ...] = ("a", "b"),
) -> tuple[TaskSpec, Path, Path, Path, Path]:
    """Freeze synthetic Pydantic input and oracle bytes independently."""
    solver = root / "solver"
    solver.mkdir()
    fixture = root / "inputs.json"
    oracle = root / "oracle.json"
    trace = solver / "trace.json"
    fixture.write_text(
        json.dumps(
            {
                "contract": "Synthetic Pydantic after-validator input",
                "cases": [
                    {"case_id": case, "left": i, "right": i + 1}
                    for i, case in enumerate(fixture_ids)
                ],
            }
        )
    )
    oracle.write_text(
        json.dumps(
            {
                "oracle_id": calibration_task().oracle_id,
                "cases": [{"case_id": case, "expected": "accepted"} for case in oracle_ids],
            }
        )
    )
    trace.write_text(
        json.dumps(
            {
                "task_id": calibration_task().task_id,
                "observations": [{"case_id": case, "actual": "accepted"} for case in observed_ids],
            }
        )
    )
    task = calibration_task().model_copy(
        update={
            "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "oracle_sha256": hashlib.sha256(oracle.read_bytes()).hexdigest(),
        }
    )
    return task, fixture, oracle, trace, solver


def run_synthetic(paths: tuple[TaskSpec, Path, Path, Path, Path]) -> OfflineScore:
    task, fixture, oracle, trace, solver = paths
    return score_observations(
        task=task,
        fixture_file=fixture,
        oracle_file=oracle,
        trace_file=trace,
        solver_workspace=solver,
    )


def test_incomplete_oracle_with_rehashed_frozen_fixture_fails_closed(tmp_path: Path) -> None:
    # Before correction this returned passed=True, assessed_cases=1, missing case b.
    paths = synthetic_case_files(tmp_path, oracle_ids=("a",), observed_ids=("a",))
    with pytest.raises(IntegrityError, match="case coverage mismatch"):
        run_synthetic(paths)


def test_complete_oracle_passes_and_uses_full_fixture_denominator(tmp_path: Path) -> None:
    score = run_synthetic(synthetic_case_files(tmp_path))
    assert score.passed is True
    assert score.assessed_cases == 2
    assert score.failed_case_ids == ()


def test_missing_observation_is_failed_not_dropped(tmp_path: Path) -> None:
    score = run_synthetic(synthetic_case_files(tmp_path, observed_ids=("a",)))
    assert score.passed is False
    assert score.assessed_cases == 2
    assert score.failed_case_ids == ("b",)


def test_unexpected_observation_is_failed_not_dropped(tmp_path: Path) -> None:
    score = run_synthetic(synthetic_case_files(tmp_path, observed_ids=("a", "b", "c")))
    assert score.passed is False
    assert score.assessed_cases == 2
    assert score.failed_case_ids == ("c",)


def test_oracle_case_not_in_frozen_fixture_is_rejected(tmp_path: Path) -> None:
    paths = synthetic_case_files(tmp_path, oracle_ids=("a", "b", "c"))
    with pytest.raises(IntegrityError, match="case coverage mismatch"):
        run_synthetic(paths)


def test_duplicate_frozen_fixture_case_is_rejected(tmp_path: Path) -> None:
    paths = synthetic_case_files(tmp_path, fixture_ids=("a", "a"), oracle_ids=("a",))
    with pytest.raises(IntegrityError, match="duplicate frozen fixture case ID"):
        run_synthetic(paths)


def test_duplicate_oracle_case_is_rejected(tmp_path: Path) -> None:
    paths = synthetic_case_files(tmp_path, oracle_ids=("a", "a", "b"))
    with pytest.raises(ValidationError, match="duplicate oracle case_id"):
        run_synthetic(paths)


def test_fixture_shape_is_strict_and_not_just_a_hash(tmp_path: Path) -> None:
    paths = synthetic_case_files(tmp_path)
    task, fixture, oracle, trace, solver = paths
    fixture.write_text(json.dumps({"contract": "wrong shape", "cases": [{"case_id": "a"}]}))
    task = task.model_copy(
        update={"fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest()}
    )
    with pytest.raises(ValidationError):
        score_observations(
            task=task,
            fixture_file=fixture,
            oracle_file=oracle,
            trace_file=trace,
            solver_workspace=solver,
        )


@pytest.mark.parametrize(
    ("case_dir", "oracle_filename", "expected_count"),
    [
        (CALIBRATION, "pydantic_after.json", 2),
        (PUBLISHED, "stdlib_trim.json", 4),
    ],
)
def test_existing_frozen_fixture_families_score_successfully(
    tmp_path: Path, case_dir: Path, oracle_filename: str, expected_count: int
) -> None:
    task = TaskSpec.model_validate_json((case_dir / "task.json").read_bytes())
    solver = tmp_path / "solver"
    solver.mkdir()
    trace = solver / "trace.json"
    oracle = E010 / "oracles" / oracle_filename
    oracle_cases = json.loads(oracle.read_text())["cases"]
    trace.write_text(
        json.dumps(
            {
                "task_id": task.task_id,
                "observations": [
                    {"case_id": case["case_id"], "actual": case["expected"]}
                    for case in oracle_cases
                ],
            }
        )
    )
    score = score_observations(
        task=task,
        fixture_file=case_dir / "inputs.json",
        oracle_file=oracle,
        trace_file=trace,
        solver_workspace=solver,
    )
    assert score.passed is True
    assert score.assessed_cases == expected_count


def manifest_for(task: TaskSpec) -> str:
    manifest = capture_unrun_manifest(
        task=task,
        condition=RetrievalCondition.BASELINE,
        budget=RetrievalBudget.BALANCED,
        project_root=ROOT,
        seed=101,
    )
    assert manifest.python_version == task.python_version
    if task.package == "python-stdlib":
        return manifest.python_version
    return manifest.package_versions[task.package]


def test_exact_pydantic_version_matches() -> None:
    assert manifest_for(calibration_task()) == "2.14.1"


def test_mismatched_pydantic_version_rejected_before_manifest() -> None:
    with pytest.raises(ValueError, match="installed package version"):
        manifest_for(calibration_task().model_copy(update={"exact_version": "999.0.0"}))


def test_non_pydantic_distribution_matches_and_mismatch_fails() -> None:
    version = importlib.metadata.version("hypothesis")
    compatible = published_task().model_copy(
        update={"package": "hypothesis", "exact_version": version}
    )
    assert manifest_for(compatible) == version
    with pytest.raises(ValueError, match="installed package version"):
        manifest_for(compatible.model_copy(update={"exact_version": "999.0.0"}))


def test_similarly_named_distribution_versions_are_not_interchangeable() -> None:
    # The installed pydantic-core is distinct from pydantic itself.
    assert importlib.metadata.version("pydantic-core") != "2.14.1"
    with pytest.raises(ValueError, match="installed package version"):
        manifest_for(
            calibration_task().model_copy(
                update={"package": "pydantic-core", "exact_version": "2.14.1"}
            )
        )


def test_stdlib_version_tracks_python_and_must_match() -> None:
    assert manifest_for(published_task()) == "3.14.10"
    with pytest.raises(ValueError, match="installed package version"):
        manifest_for(published_task().model_copy(update={"exact_version": "999.0.0"}))


def test_wrong_python_version_still_fails_before_package_check() -> None:
    with pytest.raises(ValueError, match="Python version"):
        manifest_for(calibration_task().model_copy(update={"python_version": "0.0"}))


@pytest.mark.parametrize(
    ("passed", "failures"),
    [(True, ()), (False, ("a",))],
)
def test_consistent_offline_score_is_accepted(passed: bool, failures: tuple[str, ...]) -> None:
    record = OfflineScore.model_validate_json(
        json.dumps(
            {
                "task_id": "e010-synthetic",
                "passed": passed,
                "assessed_cases": 1,
                "failed_case_ids": failures,
            }
        )
    )
    assert record.passed is passed
    assert record.failed_case_ids == failures
    assert record.scope == "offline_observation_consistency_only"


@pytest.mark.parametrize(
    ("passed", "failures"),
    [(True, ["a"]), (False, [])],
)
def test_contradictory_offline_score_json_rejected(passed: bool, failures: list[str]) -> None:
    # Before correction both contradictions were accepted by model_validate_json.
    with pytest.raises(ValidationError, match="contradicts failed case IDs"):
        OfflineScore.model_validate_json(
            json.dumps(
                {
                    "task_id": "e010-synthetic",
                    "passed": passed,
                    "assessed_cases": 1,
                    "failed_case_ids": failures,
                }
            )
        )
