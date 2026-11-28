"""Strict input contracts: frozen observations are distinct from derived reporting."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from math import isfinite
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

SHA256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
GIT_SHA = Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
EXPERIMENT_ID = Annotated[str, Field(pattern=r"^E-[0-9]{3}$")]


class Contract(BaseModel):
    """Reject unrecognized input rather than accidentally declaring verification."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ObservationState(StrEnum):
    MEASURED = "MEASURED"
    NOT_MEASURED = "NOT MEASURED"
    NOT_APPLICABLE = "NOT APPLICABLE"
    INSUFFICIENT = "INSUFFICIENT EVIDENCE"
    BLOCKED = "EXECUTION BLOCKED"


class StudyStatus(StrEnum):
    PLANNED = "PLANNED"
    PILOT = "PILOT"
    QUALIFIED = "QUALIFIED"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


class EvidenceGrade(StrEnum):
    INDEPENDENT = "independently_reproduced"
    CONTROLLED = "controlled_local"
    PILOT = "small_pilot"
    DOCUMENTATION = "documentation_only"
    ANECDOTAL = "anecdotal"
    SYNTHETIC = "synthetic_demonstration"


class Experiment(Contract):
    experiment_id: EXPERIMENT_ID
    protocol_revision: str = Field(min_length=1)
    title: str = Field(min_length=3)
    run_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,80}$")
    executed_at: datetime
    status: StudyStatus
    research_question: str = Field(min_length=5)
    hypothesis: str = Field(min_length=5)
    prespecified_criteria: str = Field(min_length=5)

    @model_validator(mode="after")
    def require_timezone(self) -> Experiment:
        if self.executed_at.utcoffset() is None:
            raise ValueError("executed_at requires an explicit UTC offset/timezone")
        return self


class Environment(Contract):
    python_implementation: str = Field(min_length=1)
    python_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+")
    interpreter_executable: str = Field(pattern=r"^/")
    uv_version: str = Field(min_length=1)
    os_name: str = Field(min_length=1)
    os_release: str = Field(min_length=1)
    architecture: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    commit_sha: GIT_SHA
    fixture_revision: str = Field(min_length=1)
    lockfile_sha256: SHA256
    pyproject_sha256: SHA256
    harness_version: str = Field(min_length=1)
    generator_version: str = Field(min_length=1)
    commands: tuple[str, ...] = Field(min_length=1)
    tool_versions: dict[str, str]
    dependency_versions: dict[str, str]
    runtime_identity: str = "local"
    hardware: str = "NOT MEASURED"
    ci_runner: str = "NOT APPLICABLE"
    selected_environment: dict[str, str] = Field(default_factory=dict)
    random_seeds: tuple[int, ...] = ()
    model_identity: str = "NOT APPLICABLE"
    agent_permissions: str = "NOT APPLICABLE"
    prompt_revision: str = "NOT APPLICABLE"
    source_retrieved_at: str = "NOT MEASURED"

    @model_validator(mode="after")
    def exclude_public_secrets(self) -> Environment:
        secret_key = re.compile(
            r"(?i)(?:^|_)(?:api_key|token|password|secret|credential|private_key)(?:_|$)"
        )
        if any(secret_key.search(key) for key in self.selected_environment):
            raise ValueError("selected_environment contains credential-like key; omit it")
        secret_value = re.compile(
            r"(?i)--(?:api-key|token|password|secret)(?:=|\s+)(?!REDACTED)(\S+)"
        )
        if any(secret_value.search(command) for command in self.commands):
            raise ValueError("execution commands contain a possible unredacted credential")
        if any(
            re.search(r"sk-[A-Za-z0-9]{12,}", value) for value in self.selected_environment.values()
        ):
            raise ValueError("selected_environment contains a token-like secret")
        return self


class Condition(Contract):
    condition_id: Literal["baseline", "candidate"]
    upstream_identity: str = Field(min_length=2)
    version: str = Field(min_length=1)
    configuration: str = Field(min_length=1)


class ReplayManifest(Contract):
    """Opt-in complete local replay population, relative to the evidence root."""

    schema_version: Literal["1.0"] = "1.0"
    members: dict[str, SHA256] = Field(min_length=1)


class Evidence(Contract):
    evidence_id: str = Field(min_length=2)
    grade: EvidenceGrade
    source: str = Field(min_length=3)
    locator: str = Field(min_length=1)
    source_sha256: SHA256 | None = None
    note: str = Field(min_length=1)
    replay_manifest: ReplayManifest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def bind_replay_anchor(self) -> Evidence:
        if self.replay_manifest is not None and (
            self.source_sha256 is None
            or self.replay_manifest.members.get(self.source) != self.source_sha256
        ):
            raise ValueError("replay manifest must bind its evidence anchor")
        return self


class Observation(Contract):
    observation_id: str = Field(min_length=2)
    condition_id: Literal["baseline", "candidate"]
    case_id: str = Field(min_length=1)
    state: ObservationState
    evidence_id: str = Field(min_length=2)
    repetition: int = Field(default=0, ge=0)
    seed: int | None = None
    expected_defect: bool | None = None
    detected_defect: bool | None = None
    duration_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    note: str = ""

    @model_validator(mode="after")
    def measured_state_consistent(self) -> Observation:
        has_detection = self.expected_defect is not None and self.detected_defect is not None
        has_partial_detection = (self.expected_defect is None) != (self.detected_defect is None)
        if has_partial_detection:
            raise ValueError("expected_defect and detected_defect must occur together")
        if self.state == ObservationState.MEASURED:
            if not has_detection and self.duration_ms is None:
                raise ValueError("measured observation requires an actual outcome or duration")
        elif has_detection or self.duration_ms is not None:
            raise ValueError("unmeasured observations cannot carry measured outcome fields")
        return self


class Criterion(Contract):
    criterion_id: str = Field(min_length=2)
    category: str = Field(min_length=2)
    dimension: str = Field(min_length=2)
    question: str = Field(min_length=5)
    metric: Literal[
        "precision",
        "recall",
        "specificity",
        "accuracy",
        "median_duration_ms",
        "unique_true_positives",
    ]
    condition_id: Literal["baseline", "candidate"]
    direction: Literal["higher", "lower"]
    thresholds: tuple[float, float, float, float]
    anchors: tuple[str, str, str, str, str]
    min_denominator: PositiveInt = 1
    required: bool = True

    @model_validator(mode="after")
    def ordered_thresholds(self) -> Criterion:
        if not all(isfinite(value) for value in self.thresholds):
            raise ValueError("thresholds must be finite")
        if self.metric == "unique_true_positives" and self.condition_id != "candidate":
            raise ValueError("unique_true_positives applies to candidate incremental signal")
        if any(
            left >= right for left, right in zip(self.thresholds, self.thresholds[1:], strict=False)
        ):
            raise ValueError("score thresholds must be strictly ascending")
        if any(not value.strip() for value in self.anchors):
            raise ValueError("every 0-4 anchor must be observable and nonempty")
        return self


class EssentialGate(Contract):
    gate_id: str = Field(min_length=2)
    requirement: str = Field(min_length=5)
    passed: bool | None
    evidence_ids: tuple[str, ...] = ()
    note: str = Field(min_length=1)


class Interpretation(Contract):
    summary: str = Field(min_length=4)
    limitations: tuple[str, ...]
    applicability: str = Field(min_length=4)
    reviewer: str = Field(min_length=1)
    disposition: str = Field(min_length=4)
    proposed_next_step: str = Field(min_length=4)


class Run(Contract):
    schema_version: Literal["1.0"]
    rubric_revision: str = Field(min_length=1)
    experiment: Experiment
    environment: Environment
    baseline: Condition
    candidate: Condition
    observations: tuple[Observation, ...]
    evidence: tuple[Evidence, ...]
    criteria: tuple[Criterion, ...]
    gates: tuple[EssentialGate, ...]
    interpretation: Interpretation
    synthetic_demonstration: bool

    @model_validator(mode="after")
    def validate_integrity(self) -> Run:
        if self.baseline.condition_id != "baseline" or self.candidate.condition_id != "candidate":
            raise ValueError("conditions must have baseline and candidate identifiers")
        evidence_ids = [receipt.evidence_id for receipt in self.evidence]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("duplicate evidence IDs")
        ids = [item.observation_id for item in self.observations]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate observation IDs")
        keys = [
            (item.condition_id, item.case_id, item.repetition, item.seed)
            for item in self.observations
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate observation case/repetition/seed identity")
        if len({c.criterion_id for c in self.criteria}) != len(self.criteria):
            raise ValueError("duplicate criterion ID")
        if len({g.gate_id for g in self.gates}) != len(self.gates):
            raise ValueError("duplicate gate ID")
        oracle_by_case: dict[str, bool] = {}
        for item in self.observations:
            if item.evidence_id not in evidence_ids:
                raise ValueError(f"observation refers to unknown evidence {item.evidence_id}")
            # The case ID denotes a fixed fixture and fixed independent reference truth.
            # Repetitions/seeds may change predictions, never the case's oracle.
            if item.expected_defect is not None:
                known = oracle_by_case.get(item.case_id)
                if known is not None and known != item.expected_defect:
                    raise ValueError(
                        f"reference-oracle conflict for case_id={item.case_id!r}: "
                        "expected_defect differs across conditions or repetitions; "
                        "use distinct case IDs for distinct oracle truths"
                    )
                oracle_by_case[item.case_id] = item.expected_defect
        for gate in self.gates:
            if any(ref not in evidence_ids for ref in gate.evidence_ids):
                raise ValueError(f"gate {gate.gate_id} refers to unknown evidence")
            if gate.passed is True and not gate.evidence_ids:
                raise ValueError(f"passed gate {gate.gate_id} needs evidence")
        receipt_grades = {e.evidence_id: e.grade for e in self.evidence}
        measured_grades = {
            receipt_grades[o.evidence_id]
            for o in self.observations
            if o.state == ObservationState.MEASURED
        }
        # The legacy input flag cannot suppress synthetic provenance, whether
        # synthetic measured observations are the whole dataset or one arm.
        # Grades remain source declarations, NOT independently attested evidence.
        if EvidenceGrade.SYNTHETIC in measured_grades and not self.synthetic_demonstration:
            raise ValueError(
                "synthetic measured evidence requires synthetic_demonstration=true, "
                "including mixed synthetic and nonsynthetic source declarations"
            )
        if self.synthetic_demonstration and not any(
            e.grade == EvidenceGrade.SYNTHETIC for e in self.evidence
        ):
            raise ValueError("synthetic demonstration must declare synthetic evidence")
        return self
