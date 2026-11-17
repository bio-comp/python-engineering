"""E-010 calibration, integrity and non-efficacy proof obligations."""

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from python_engineering.e010.contracts import (
    FixtureTier,
    ObservationTrace,
    RetrievalBudget,
    RetrievalCondition,
    RunManifest,
    TaskSpec,
    TrialRecord,
)
from python_engineering.e010.demo import main, run_demo
from python_engineering.e010.provenance import capture_unrun_manifest, write_new_record
from python_engineering.e010.scoring import IntegrityError, score_observations

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / "experiments" / "e010"
PUBLISHED = EXPERIMENT / "fixtures" / "published_test"


def task() -> TaskSpec:
    return TaskSpec.model_validate_json((PUBLISHED / "task.json").read_bytes())


def base_manifest(condition: RetrievalCondition = RetrievalCondition.BASELINE) -> RunManifest:
    return RunManifest(
        task_id="e010-stdlib-strip",
        condition=condition,
        retrieval_budget=RetrievalBudget.BALANCED,
        model_id=None,
        model_settings_sha256=None,
        agent_config_sha256=None,
        python_version="3.14.10",
        package_versions={"pydantic": "2.14.1"},
        os_platform="synthetic-no-claim",
        git_sha="0" * 40,
        fixture_sha256="0" * 64,
        seed=101,
        workspace_dirty=False,
        declared_target_tools=tuple(sorted(condition.target_tools)),
        observed_target_tools=None,
        declared_non_target_tools=("python",),
        observed_non_target_tools=None,
        isolation_receipt_id=None,
        agent_tool_events_available=False,
        tokens_available=False,
        wall_time_available=False,
        money_available=False,
    )


def test_four_arms_are_distinct_and_preserve_baseline() -> None:
    assert {arm.value for arm in RetrievalCondition} == {"A", "B", "C", "D"}
    assert [arm.target_tools for arm in RetrievalCondition] == [
        frozenset(),
        frozenset({"context7"}),
        frozenset({"sofa"}),
        frozenset({"context7", "sofa"}),
    ]


@pytest.mark.parametrize("condition", list(RetrievalCondition))
def test_unobserved_permissions_never_qualify_condition(condition: RetrievalCondition) -> None:
    manifest = base_manifest(condition)
    failures = manifest.scored_readiness_failures()
    assert "target_tool_access_unverified" in failures
    assert "agent_oracle_isolation_unverified" in failures
    assert "agent_tool_events_unavailable" in failures
    with pytest.raises(ValidationError):
        TrialRecord(manifest=manifest, status="scored", correctness=True, invalid_reason=None)
    record = TrialRecord(manifest=manifest, status="not_run", correctness=None, invalid_reason=None)
    assert record.money_usd is None
    assert record.token_count is None


def test_invalid_comparisons_rejected_when_tools_differ() -> None:
    m = base_manifest(RetrievalCondition.CONTEXT7).model_copy(
        update={"observed_target_tools": ("sofa",), "observed_non_target_tools": ("python",)}
    )
    assert "target_tool_access_unverified" in m.scored_readiness_failures()
    assert "non_target_tool_access_unverified" not in m.scored_readiness_failures()


def test_required_fields_unknown_fields_and_traversal_are_rejected() -> None:
    fields = task().model_dump(mode="json")
    fields["permitted_files"] = ["../private.py"]
    with pytest.raises(ValidationError):
        TaskSpec.model_validate_json(json.dumps(fields))
    fields = task().model_dump(mode="json")
    fields["extra"] = "unexpected"
    with pytest.raises(ValidationError):
        TaskSpec.model_validate_json(json.dumps(fields))
    fields.pop("extra")
    fields.pop("oracle_sha256")
    with pytest.raises(ValidationError):
        TaskSpec.model_validate_json(json.dumps(fields))


def test_published_test_is_not_sequestered() -> None:
    assert task().tier is FixtureTier.PUBLISHED_TEST
    calibration = EXPERIMENT / "fixtures" / "calibration" / "task.json"
    assert TaskSpec.model_validate_json(calibration.read_bytes()).tier is FixtureTier.CALIBRATION


def test_demo_distinguishes_valid_and_known_bad_without_agent_run() -> None:
    result = run_demo(ROOT)
    assert result["valid_observation_passed"] is True
    assert result["known_bad_observation_rejected"] is True
    assert result["agent_trials_run"] == 0
    assert result["cases_assessed"] == 4


def test_hash_tampering_fails_closed(tmp_path: Path) -> None:
    oracle = tmp_path / "oracle.json"
    oracle.write_bytes((EXPERIMENT / "oracles" / "stdlib_trim.json").read_bytes() + b" ")
    solver = tmp_path / "solver"
    solver.mkdir()
    trace = solver / "output.json"
    trace.write_bytes((PUBLISHED / "observed_valid.json").read_bytes())
    with pytest.raises(IntegrityError, match="oracle hash"):
        score_observations(
            task=task(),
            fixture_file=PUBLISHED / "inputs.json",
            oracle_file=oracle,
            trace_file=trace,
            solver_workspace=solver,
        )


def test_oracle_in_solver_workspace_fails_closed(tmp_path: Path) -> None:
    solver = tmp_path / "solver"
    solver.mkdir()
    oracle = solver / "oracle.json"
    oracle.write_bytes((EXPERIMENT / "oracles" / "stdlib_trim.json").read_bytes())
    trace = solver / "trace.json"
    trace.write_bytes((PUBLISHED / "observed_valid.json").read_bytes())
    with pytest.raises(IntegrityError, match="oracle resides"):
        score_observations(
            task=task(),
            fixture_file=PUBLISHED / "inputs.json",
            oracle_file=oracle,
            trace_file=trace,
            solver_workspace=solver,
        )


def test_missing_case_rejected(tmp_path: Path) -> None:
    solver = tmp_path / "solver"
    solver.mkdir()
    trace = json.loads((PUBLISHED / "observed_valid.json").read_text())
    trace["observations"].pop()
    trace_path = solver / "trace.json"
    trace_path.write_text(json.dumps(trace))
    result = score_observations(
        task=task(),
        fixture_file=PUBLISHED / "inputs.json",
        oracle_file=EXPERIMENT / "oracles" / "stdlib_trim.json",
        trace_file=trace_path,
        solver_workspace=solver,
    )
    assert not result.passed
    assert result.failed_case_ids == ("unicode",)


def test_duplicate_trace_case_rejected() -> None:
    payload = json.loads((PUBLISHED / "observed_valid.json").read_text())
    payload["observations"].append(payload["observations"][0])
    with pytest.raises(ValidationError, match="duplicate"):
        ObservationTrace.model_validate_json(json.dumps(payload))


def test_capture_unrun_provenance_and_exclusive_artifact(tmp_path: Path) -> None:
    manifest = capture_unrun_manifest(
        task=task(),
        condition=RetrievalCondition.SOFA,
        budget=RetrievalBudget.AGENT_DIRECTED,
        project_root=ROOT,
        seed=101,
    )
    assert manifest.model_id is None
    assert manifest.agent_tool_events_available is False
    assert manifest.python_version == "3.14.10"
    assert re.fullmatch(r"[0-9a-f]{40}", manifest.git_sha)
    artifact = tmp_path / "manifest.json"
    digest = write_new_record(artifact, manifest)
    assert digest == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert RunManifest.model_validate_json(artifact.read_bytes()) == manifest
    with pytest.raises(FileExistsError):
        write_new_record(artifact, manifest)


@given(st.text(max_size=200))
def test_valid_alternative_trim_matches_python_strip(payload: str) -> None:
    # Independent algorithm via explicit boundary scans, without calling strip().
    lo, hi = 0, len(payload)
    while lo < hi and payload[lo].isspace():
        lo += 1
    while hi > lo and payload[hi - 1].isspace():
        hi -= 1
    assert payload[lo:hi] == payload.strip()


def test_known_bad_lstrip_is_not_an_equivalent_implementation() -> None:
    inputs = json.loads((PUBLISHED / "inputs.json").read_text())["cases"]
    assert any(case["input"].lstrip() != case["input"].strip() for case in inputs)


def test_norun_record_rejects_fabricated_telemetry() -> None:
    with pytest.raises(ValidationError):
        TrialRecord(
            manifest=base_manifest(),
            status="not_run",
            correctness=None,
            invalid_reason=None,
            money_usd=0.0,
        )


@pytest.mark.parametrize("unsafe_path", ["/tmp/private.py", ".", "../../escape.py"])
def test_path_fails_even_when_other_fields_valid(unsafe_path: str) -> None:
    payload = task().model_dump(mode="json")
    payload["permitted_files"] = [unsafe_path]
    with pytest.raises(ValidationError, match="permitted paths"):
        TaskSpec.model_validate_json(json.dumps(payload))


def test_duplicate_permitted_files_rejected() -> None:
    payload = task().model_dump(mode="json")
    payload["permitted_files"] = ["solution.py", "solution.py"]
    with pytest.raises(ValidationError, match="unique"):
        TaskSpec.model_validate_json(json.dumps(payload))


def test_comparison_readiness_requirements_are_structural_not_authentication() -> None:
    m = base_manifest(RetrievalCondition.COMBINED)
    assert "model_identity_unavailable" in m.scored_readiness_failures()
    assert "agent_configuration_unavailable" in m.scored_readiness_failures()
    complete = m.model_copy(
        update={
            "model_id": "synthetic-not-executed",
            "model_settings_sha256": "1" * 64,
            "agent_config_sha256": "2" * 64,
            "observed_target_tools": ("context7", "sofa"),
            "observed_non_target_tools": ("python",),
            "isolation_receipt_id": "untrusted-placeholder-not-proof",
            "agent_tool_events_available": True,
        }
    )
    # Schema-level consistency is NOT authentication of access, event logs or receipts.
    assert complete.scored_readiness_failures() == ()
    incorrect = complete.model_copy(update={"declared_target_tools": ("sofa",)})
    assert "incorrect_target_tool_declaration" in incorrect.scored_readiness_failures()
    dirty = complete.model_copy(update={"workspace_dirty": True})
    assert "workspace_contains_uncommitted_changes" in dirty.scored_readiness_failures()
    missing_events = complete.model_copy(update={"agent_tool_events_available": False})
    assert "agent_tool_events_unavailable" in missing_events.scored_readiness_failures()


@pytest.mark.parametrize(
    ("status", "correctness", "invalid_reason"),
    [
        ("not_run", None, "unexpected"),
        ("invalid", None, None),
        ("scored", None, None),
    ],
)
def test_invalid_status_outcome_combinations_fail(
    status: str, correctness: bool | None, invalid_reason: str | None
) -> None:
    with pytest.raises(ValidationError):
        TrialRecord(
            manifest=base_manifest(),
            status=status,
            correctness=correctness,
            invalid_reason=invalid_reason,
        )


def test_forged_scored_status_rejected_but_offline_outcome_is_recordable() -> None:
    manifest = base_manifest()
    with pytest.raises(ValidationError):
        TrialRecord(manifest=manifest, status="scored", correctness=True, invalid_reason=None)
    offline = TrialRecord(
        manifest=manifest,
        status="offline_trace_compared",
        correctness=False,
        invalid_reason=None,
    )
    assert offline.correctness is False
    with pytest.raises(ValidationError):
        TrialRecord(
            manifest=manifest,
            status="offline_trace_compared",
            correctness=None,
            invalid_reason=None,
        )


def test_fixture_hash_tamper_rejected(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_bytes((PUBLISHED / "inputs.json").read_bytes() + b"\n")
    solver = tmp_path / "solver"
    solver.mkdir()
    trace = solver / "trace.json"
    trace.write_bytes((PUBLISHED / "observed_valid.json").read_bytes())
    with pytest.raises(IntegrityError, match="fixture hash"):
        score_observations(
            task=task(),
            fixture_file=fixture,
            oracle_file=EXPERIMENT / "oracles" / "stdlib_trim.json",
            trace_file=trace,
            solver_workspace=solver,
        )


def test_outside_trace_and_identity_mismatch_fail(tmp_path: Path) -> None:
    solver = tmp_path / "solver"
    solver.mkdir()
    trace = tmp_path / "outside.json"
    trace.write_bytes((PUBLISHED / "observed_valid.json").read_bytes())
    with pytest.raises(IntegrityError, match="designated workspace"):
        score_observations(
            task=task(),
            fixture_file=PUBLISHED / "inputs.json",
            oracle_file=EXPERIMENT / "oracles" / "stdlib_trim.json",
            trace_file=trace,
            solver_workspace=solver,
        )
    trace = solver / "trace.json"
    payload = json.loads((PUBLISHED / "observed_valid.json").read_text())
    payload["task_id"] = "e010-other-task"
    trace.write_text(json.dumps(payload))
    with pytest.raises(IntegrityError, match="identity mismatch"):
        score_observations(
            task=task(),
            fixture_file=PUBLISHED / "inputs.json",
            oracle_file=EXPERIMENT / "oracles" / "stdlib_trim.json",
            trace_file=trace,
            solver_workspace=solver,
        )


def test_provenance_rejects_wrong_interpreter_and_records_deps() -> None:
    with pytest.raises(ValueError, match="Python version"):
        capture_unrun_manifest(
            task=task().model_copy(update={"python_version": "0.0"}),
            condition=RetrievalCondition.BASELINE,
            budget=RetrievalBudget.BALANCED,
            project_root=ROOT,
            seed=101,
        )
    extra = task().model_copy(update={"package": "hypothesis"})
    m = capture_unrun_manifest(
        task=extra,
        condition=RetrievalCondition.BASELINE,
        budget=RetrievalBudget.BALANCED,
        project_root=ROOT,
        seed=101,
    )
    assert m.package_versions["hypothesis"].startswith("6.")


def test_cli_records_four_real_unrun_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "records"
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(sys, "argv", ["e010-demo", "--manifest-dir", str(output)])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["agent_trials_run"] == 0
    assert result["not_run_manifest_count"] == 4
    assert len(list(output.glob("*.json"))) == 4
    for condition in RetrievalCondition:
        artifact = output / f"condition-{condition.value}-not-run.json"
        record = TrialRecord.model_validate_json(artifact.read_bytes())
        assert record.status == "not_run"
        assert record.correctness is None
        assert record.manifest.model_id is None
        assert record.manifest.condition == condition
        assert (
            result[f"condition_{condition.value}_record_sha256"]
            == hashlib.sha256(artifact.read_bytes()).hexdigest()
        )
    with pytest.raises(FileExistsError):
        main()
