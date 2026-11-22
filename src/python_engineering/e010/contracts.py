"""Versioned, fail-closed contracts for the four-arm E-010 protocol."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SHA256 = r"^[0-9a-f]{64}$"
GIT_SHA = r"^[0-9a-f]{40}$"


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RetrievalCondition(StrEnum):
    BASELINE = "A"
    CONTEXT7 = "B"
    SOFA = "C"
    COMBINED = "D"

    @property
    def target_tools(self) -> frozenset[str]:
        return {
            self.BASELINE: frozenset(),
            self.CONTEXT7: frozenset({"context7"}),
            self.SOFA: frozenset({"sofa"}),
            self.COMBINED: frozenset({"context7", "sofa"}),
        }[self]


class RetrievalBudget(StrEnum):
    BALANCED = "balanced"
    AGENT_DIRECTED = "agent_directed"


class FixtureTier(StrEnum):
    CALIBRATION = "calibration"
    PUBLISHED_TEST = "published_test"
    SEQUESTERED = "sequestered"


class TaskSpec(StrictRecord):
    task_id: str = Field(pattern=r"^e010-[a-z0-9-]+$")
    package: str = Field(min_length=1)
    exact_version: str = Field(min_length=1)
    python_version: str = Field(min_length=1)
    acceptance_contract: str = Field(min_length=1)
    oracle_id: str = Field(min_length=1)
    oracle_sha256: str = Field(pattern=SHA256)
    fixture_sha256: str = Field(pattern=SHA256)
    permitted_files: tuple[str, ...] = Field(min_length=1)
    tier: FixtureTier

    @model_validator(mode="after")
    def reject_unbounded_paths(self) -> Self:
        from pathlib import PurePosixPath

        for raw_path in self.permitted_files:
            path = PurePosixPath(raw_path)
            if not raw_path or path.is_absolute() or ".." in path.parts or "." == raw_path:
                raise ValueError("permitted paths must be relative and non-traversing")
        if len(set(self.permitted_files)) != len(self.permitted_files):
            raise ValueError("permitted_files must be unique")
        return self


class RunManifest(StrictRecord):
    task_id: str = Field(min_length=1)
    condition: RetrievalCondition
    retrieval_budget: RetrievalBudget
    model_id: str | None
    model_settings_sha256: str | None = Field(pattern=SHA256)
    agent_config_sha256: str | None = Field(pattern=SHA256)
    python_version: str = Field(min_length=1)
    package_versions: dict[str, str]
    os_platform: str = Field(min_length=1)
    git_sha: str = Field(pattern=GIT_SHA)
    fixture_sha256: str = Field(pattern=SHA256)
    seed: int = Field(ge=0)
    workspace_dirty: bool
    declared_target_tools: tuple[str, ...]
    observed_target_tools: tuple[str, ...] | None
    declared_non_target_tools: tuple[str, ...]
    observed_non_target_tools: tuple[str, ...] | None
    isolation_receipt_id: str | None
    agent_tool_events_available: bool
    tokens_available: bool
    wall_time_available: bool
    money_available: bool

    def scored_readiness_failures(self) -> tuple[str, ...]:
        """Find unproven conditions; manifests alone cannot authenticate receipts."""
        failures: list[str] = []
        if self.workspace_dirty:
            failures.append("workspace_contains_uncommitted_changes")
        if self.model_id is None or self.model_settings_sha256 is None:
            failures.append("model_identity_unavailable")
        if self.agent_config_sha256 is None:
            failures.append("agent_configuration_unavailable")
        expected = self.condition.target_tools
        if set(self.declared_target_tools) != expected:
            failures.append("incorrect_target_tool_declaration")
        if self.observed_target_tools is None or set(self.observed_target_tools) != expected:
            failures.append("target_tool_access_unverified")
        if self.observed_non_target_tools is None or set(self.observed_non_target_tools) != set(
            self.declared_non_target_tools
        ):
            failures.append("non_target_tool_access_unverified")
        if self.isolation_receipt_id is None:
            failures.append("agent_oracle_isolation_unverified")
        if not self.agent_tool_events_available:
            failures.append("agent_tool_events_unavailable")
        return tuple(failures)


class PydanticAfterInputCase(StrictRecord):
    case_id: str = Field(min_length=1)
    left: int
    right: int


class StdlibStripInputCase(StrictRecord):
    case_id: str = Field(min_length=1)
    input: str


class PydanticAfterInputs(StrictRecord):
    contract: str = Field(min_length=1)
    cases: tuple[PydanticAfterInputCase, ...] = Field(min_length=1)


class StdlibStripInputs(StrictRecord):
    contract: str = Field(min_length=1)
    cases: tuple[StdlibStripInputCase, ...] = Field(min_length=1)


class OracleCase(StrictRecord):
    case_id: str = Field(min_length=1)
    expected: str


class OracleSpec(StrictRecord):
    oracle_id: str = Field(min_length=1)
    cases: tuple[OracleCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_cases(self) -> Self:
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("duplicate oracle case_id")
        return self


class ObservedCase(StrictRecord):
    case_id: str = Field(min_length=1)
    actual: str


class ObservationTrace(StrictRecord):
    task_id: str = Field(min_length=1)
    observations: tuple[ObservedCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_cases(self) -> Self:
        if len({case.case_id for case in self.observations}) != len(self.observations):
            raise ValueError("duplicate observed case_id")
        return self


class OfflineScore(StrictRecord):
    task_id: str
    passed: bool
    assessed_cases: int = Field(ge=0)
    failed_case_ids: tuple[str, ...]
    scope: Literal["offline_observation_consistency_only"] = "offline_observation_consistency_only"

    @model_validator(mode="after")
    def consistent_pass_status(self) -> Self:
        if self.passed == bool(self.failed_case_ids):
            raise ValueError("offline pass status contradicts failed case IDs")
        return self


class TrialRecord(StrictRecord):
    manifest: RunManifest
    status: str = Field(pattern=r"^(not_run|invalid|offline_trace_compared)$")
    correctness: bool | None
    invalid_reason: str | None
    token_count: int | None = Field(default=None, ge=0)
    wall_time_seconds: float | None = Field(default=None, ge=0)
    money_usd: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def prevent_invented_outcomes(self) -> Self:
        if self.status != "offline_trace_compared" and self.correctness is not None:
            raise ValueError("no correctness claim without an observation comparison")
        if self.status == "offline_trace_compared" and self.correctness is None:
            raise ValueError("an offline comparison requires an observed outcome")
        if self.status == "not_run" and (
            self.invalid_reason is not None
            or self.token_count is not None
            or self.wall_time_seconds is not None
            or self.money_usd is not None
        ):
            raise ValueError("not-run trials have no outcomes or telemetry")
        if self.status == "invalid" and self.invalid_reason is None:
            raise ValueError("invalid trials require a reason")
        return self
