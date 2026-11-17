"""Compare external observations to a separately located immutable oracle.

This module NEVER imports or executes candidate code. A trusted, isolated
execution runner is not yet implemented and cannot be inferred from traces.
"""

from pathlib import Path

from python_engineering.digests import sha256_file
from python_engineering.e010.contracts import ObservationTrace, OfflineScore, OracleSpec, TaskSpec


class IntegrityError(ValueError):
    """Mismatch in identity, location, access or frozen fixture bytes."""


def score_observations(
    *,
    task: TaskSpec,
    fixture_file: Path,
    oracle_file: Path,
    trace_file: Path,
    solver_workspace: Path,
) -> OfflineScore:
    """Check external trace bytes; path separation is not OS-level isolation."""
    solver = solver_workspace.resolve(strict=True)
    if oracle_file.resolve(strict=True).is_relative_to(solver):
        raise IntegrityError("oracle resides inside solver workspace")
    if fixture_file.resolve(strict=True).is_relative_to(solver):
        raise IntegrityError("fixture contract resides inside solver workspace")
    if not trace_file.resolve(strict=True).is_relative_to(solver):
        raise IntegrityError("observations are not from the designated workspace")
    if sha256_file(oracle_file) != task.oracle_sha256:
        raise IntegrityError("oracle hash differs from frozen task contract")
    if sha256_file(fixture_file) != task.fixture_sha256:
        raise IntegrityError("fixture hash differs from frozen task contract")

    oracle = OracleSpec.model_validate_json(oracle_file.read_bytes())
    trace = ObservationTrace.model_validate_json(trace_file.read_bytes())
    if oracle.oracle_id != task.oracle_id or trace.task_id != task.task_id:
        raise IntegrityError("task/oracle/trace identity mismatch")
    expected = {case.case_id: case.expected for case in oracle.cases}
    observed = {case.case_id: case.actual for case in trace.observations}
    ids = expected.keys() | observed.keys()
    failed = tuple(sorted(k for k in ids if expected.get(k) != observed.get(k)))
    return OfflineScore(
        task_id=task.task_id,
        passed=not failed,
        assessed_cases=len(expected),
        failed_case_ids=failed,
    )
