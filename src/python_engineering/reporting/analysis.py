"""Descriptive-only evaluation; no IID assumptions from repeated fixture executions."""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from pydantic import Field

from python_engineering.reporting.models import (
    Contract,
    Criterion,
    EvidenceGrade,
    Observation,
    ObservationState,
    Run,
)


class ConditionMetrics(Contract):
    condition_id: str
    recorded_rows: int
    measured_rows: int
    detection_rows: int
    tp: int
    fp: int
    tn: int
    fn: int
    precision: float | None
    recall: float | None
    specificity: float | None
    accuracy: float | None
    median_duration_ms: float | None
    duration_count: int


class PairedMetrics(Contract):
    matched_detection_pairs: int
    baseline_only_correct: int
    candidate_only_correct: int
    both_correct: int
    both_wrong: int
    candidate_minus_baseline_accuracy: float | None
    unique_true_positives: int
    interpretation: str = (
        "Descriptive paired comparisons on matched fixture/repetition/seed only; "
        "repeated invocations do not establish independent tasks or a population interval."
    )


class CriterionResult(Contract):
    criterion_id: str
    dimension: str
    category: str
    question: str
    metric: str
    condition_id: str
    value: float | None
    denominator: int
    score: int | None = Field(default=None, ge=0, le=4)
    state: ObservationState
    evidence_grade: str
    anchors: tuple[str, str, str, str, str]
    evidence_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]
    explanation: str


class Analysis(Contract):
    baseline: ConditionMetrics
    candidate: ConditionMetrics
    paired: PairedMetrics
    criteria: tuple[CriterionResult, ...]
    essential_gate_state: str
    required_criteria_state: str
    unscored_required_criteria: tuple[str, ...]
    evaluation_readiness: str
    evidence_classification: str
    statistical_scope: str = (
        "Descriptive counts, proportions, and medians only; no confidence "
        "intervals/p-values without an independently specified sampling design."
    )


def condition_metrics(observations: tuple[Observation, ...], condition_id: str) -> ConditionMetrics:
    selected = [o for o in observations if o.condition_id == condition_id]
    measured = [o for o in selected if o.state == ObservationState.MEASURED]
    detection = [o for o in measured if o.expected_defect is not None]
    tp = sum(o.expected_defect is True and o.detected_defect is True for o in detection)
    fp = sum(o.expected_defect is False and o.detected_defect is True for o in detection)
    tn = sum(o.expected_defect is False and o.detected_defect is False for o in detection)
    fn = sum(o.expected_defect is True and o.detected_defect is False for o in detection)
    durations = [o.duration_ms for o in measured if o.duration_ms is not None]
    return ConditionMetrics(
        condition_id=condition_id,
        recorded_rows=len(selected),
        measured_rows=len(measured),
        detection_rows=len(detection),
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / (tp + fn) if tp + fn else None,
        specificity=tn / (tn + fp) if tn + fp else None,
        accuracy=(tp + tn) / len(detection) if detection else None,
        median_duration_ms=median(durations) if durations else None,
        duration_count=len(durations),
    )


def paired_metrics(observations: tuple[Observation, ...]) -> PairedMetrics:
    by_condition: dict[str, dict[tuple[str, int, int | None], Observation]] = defaultdict(dict)
    for o in observations:
        if o.state == ObservationState.MEASURED and o.expected_defect is not None:
            by_condition[o.condition_id][(o.case_id, o.repetition, o.seed)] = o
    pairs = sorted(
        set(by_condition["baseline"]).intersection(by_condition["candidate"]),
        key=lambda item: (item[0], item[1], str(item[2])),
    )
    baseline_wins = candidate_wins = both_correct = both_wrong = unique_tp = 0
    for key in pairs:
        b, c = by_condition["baseline"][key], by_condition["candidate"][key]
        b_ok = b.expected_defect == b.detected_defect
        c_ok = c.expected_defect == c.detected_defect
        if b_ok and c_ok:
            both_correct += 1
        elif b_ok:
            baseline_wins += 1
        elif c_ok:
            candidate_wins += 1
        else:
            both_wrong += 1
        if b.expected_defect is True and b.detected_defect is False and c.detected_defect:
            unique_tp += 1
    n = len(pairs)
    return PairedMetrics(
        matched_detection_pairs=n,
        baseline_only_correct=baseline_wins,
        candidate_only_correct=candidate_wins,
        both_correct=both_correct,
        both_wrong=both_wrong,
        candidate_minus_baseline_accuracy=(candidate_wins - baseline_wins) / n if n else None,
        unique_true_positives=unique_tp,
    )


def measured_evidence_classification(run: Run) -> str:
    """Classify measured provenance, never implying authenticated external evidence."""
    grade_by_id = {e.evidence_id: e.grade for e in run.evidence}
    grades = {
        grade_by_id[o.evidence_id] for o in run.observations if o.state == ObservationState.MEASURED
    }
    if not grades:
        return "NO MEASURED EVIDENCE"
    synthetic = EvidenceGrade.SYNTHETIC in grades
    if synthetic and len(grades) == 1:
        return "SYNTHETIC-ONLY MEASURED EVIDENCE"
    if synthetic:
        return "MIXED SYNTHETIC AND NONSYNTHETIC DECLARATIONS"
    return "NONSYNTHETIC SOURCE DECLARATIONS - NOT ATTESTED"


def _support_for(rule: Criterion, run: Run) -> tuple[Observation, ...]:
    """Return precisely those observations whose measured values enter the metric."""
    measured = [o for o in run.observations if o.state == ObservationState.MEASURED]
    if rule.metric == "unique_true_positives":
        by_condition = {
            condition: {
                (o.case_id, o.repetition, o.seed): o
                for o in measured
                if o.condition_id == condition and o.expected_defect is not None
            }
            for condition in ("baseline", "candidate")
        }
        matched = set(by_condition["baseline"]) & set(by_condition["candidate"])
        return tuple(
            o
            for o in measured
            if o.expected_defect is not None and (o.case_id, o.repetition, o.seed) in matched
        )
    selected = (o for o in measured if o.condition_id == rule.condition_id)
    if rule.metric == "median_duration_ms":
        return tuple(o for o in selected if o.duration_ms is not None)
    detection = (o for o in selected if o.expected_defect is not None)
    if rule.metric == "precision":
        return tuple(o for o in detection if o.detected_defect is True)
    if rule.metric == "recall":
        return tuple(o for o in detection if o.expected_defect is True)
    if rule.metric == "specificity":
        return tuple(o for o in detection if o.expected_defect is False)
    return tuple(detection)


def _support_grade(run: Run, evidence_ids: tuple[str, ...]) -> str:
    receipts = {e.evidence_id: e for e in run.evidence}
    grades = {receipts[eid].grade.value for eid in evidence_ids}
    if not grades:
        return "NOT MEASURED"
    if len(grades) != 1:
        return "mixed (" + ", ".join(sorted(grades)) + ")"
    return next(iter(grades))


def _criterion(
    rule: Criterion,
    run: Run,
    base: ConditionMetrics,
    cand: ConditionMetrics,
    paired: PairedMetrics,
) -> CriterionResult:
    metrics = base if rule.condition_id == "baseline" else cand
    metric_name = rule.metric
    denominator = metrics.detection_rows
    value: float | None
    if metric_name == "precision":
        value, denominator = metrics.precision, metrics.tp + metrics.fp
    elif metric_name == "recall":
        value, denominator = metrics.recall, metrics.tp + metrics.fn
    elif metric_name == "specificity":
        value, denominator = metrics.specificity, metrics.tn + metrics.fp
    elif metric_name == "accuracy":
        value = metrics.accuracy
    elif metric_name == "median_duration_ms":
        value, denominator = metrics.median_duration_ms, metrics.duration_count
    else:
        value, denominator = float(paired.unique_true_positives), paired.matched_detection_pairs
    contributors = _support_for(rule, run)
    evidence_refs = tuple(sorted({o.evidence_id for o in contributors}))
    observation_refs = tuple(sorted(o.observation_id for o in contributors))
    # Denominators are derived by the same metric predicates above; these
    # observations support both the numerator and the relevant denominator.
    expected_support = denominator * (2 if metric_name == "unique_true_positives" else 1)
    if len(contributors) != expected_support:
        raise ValueError(f"support/denominator mismatch for {rule.criterion_id}")
    if denominator < rule.min_denominator or value is None:
        score, state = None, ObservationState.INSUFFICIENT
        explanation = (
            f"Only {denominator} applicable observations; minimum {rule.min_denominator}. "
            "No score assigned."
        )
    else:
        score = sum(
            value >= threshold if rule.direction == "higher" else value <= threshold
            for threshold in rule.thresholds
        )
        state = ObservationState.MEASURED
        explanation = (
            f"Mechanically derived from {metric_name}={value:.6g} "
            f"(denominator={denominator}); thresholds={rule.thresholds}. "
            "This is a criterion outcome, not an adoption or evidence-strength claim."
        )
    return CriterionResult(
        criterion_id=rule.criterion_id,
        dimension=rule.dimension,
        category=rule.category,
        question=rule.question,
        metric=metric_name,
        condition_id=rule.condition_id,
        value=value,
        denominator=denominator,
        score=score,
        state=state,
        evidence_grade=_support_grade(run, evidence_refs),
        anchors=rule.anchors,
        evidence_ids=evidence_refs,
        observation_ids=observation_refs,
        explanation=explanation,
    )


def analyze(run: Run) -> Analysis:
    """Calculate from validated observations only; never impute unknown results."""
    classification = measured_evidence_classification(run)
    baseline = condition_metrics(run.observations, "baseline")
    candidate = condition_metrics(run.observations, "candidate")
    paired = paired_metrics(run.observations)
    if any(g.passed is False for g in run.gates):
        gate_state = "FAILED - NONCOMPENSATORY"
    elif any(g.passed is None for g in run.gates) or not run.gates:
        gate_state = "UNKNOWN - NOT QUALIFIED"
    else:
        gate_state = "ALL RECORDED GATES PASSED - ADOPTION STILL REQUIRES AUTHORITY"
    results = tuple(_criterion(rule, run, baseline, candidate, paired) for rule in run.criteria)
    missing_required = tuple(
        result.criterion_id
        for rule, result in zip(run.criteria, results, strict=True)
        if rule.required and result.score is None
    )
    if not any(rule.required for rule in run.criteria):
        criterion_state = "NOT SPECIFIED - NO REQUIRED CRITERIA"
    elif missing_required:
        criterion_state = "INCOMPLETE - UNSCORED REQUIRED CRITERIA"
    else:
        criterion_state = "COMPLETE - ALL REQUIRED CRITERIA SCORED"
    if any(g.passed is False for g in run.gates):
        readiness = "BLOCKED - ESSENTIAL GATE FAILED"
    elif any(g.passed is None for g in run.gates) or not run.gates:
        readiness = "INCOMPLETE - ESSENTIAL GATES UNKNOWN"
    elif criterion_state != "COMPLETE - ALL REQUIRED CRITERIA SCORED":
        readiness = "INCOMPLETE - REQUIRED MEASUREMENTS"
    elif classification == "MIXED SYNTHETIC AND NONSYNTHETIC DECLARATIONS":
        readiness = "INCOMPLETE - SYNTHETIC MEASURED EVIDENCE"
    elif classification == "SYNTHETIC-ONLY MEASURED EVIDENCE" or run.synthetic_demonstration:
        # A model_copy(update=...) can bypass Pydantic validators: analysis must
        # remain conservative independently of the public ingestion boundary.
        readiness = "INCOMPLETE - SYNTHETIC DEMONSTRATION"
    else:
        readiness = "RECORDED REQUIREMENTS MET - NO ADOPTION INFERRED"
    return Analysis(
        baseline=baseline,
        candidate=candidate,
        paired=paired,
        criteria=results,
        essential_gate_state=gate_state,
        required_criteria_state=criterion_state,
        unscored_required_criteria=missing_required,
        evaluation_readiness=readiness,
        evidence_classification=classification,
    )
