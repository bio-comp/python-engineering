"""Descriptive-only evaluation; no IID assumptions from repeated fixture executions."""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from pydantic import Field

from python_engineering.reporting.models import (
    Contract,
    Criterion,
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
    explanation: str


class Analysis(Contract):
    baseline: ConditionMetrics
    candidate: ConditionMetrics
    paired: PairedMetrics
    criteria: tuple[CriterionResult, ...]
    essential_gate_state: str
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
        if b.expected_defect != c.expected_defect:
            raise ValueError("paired oracle conflict for identical fixture/repetition/seed")
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


def _grade_for(run: Run, condition: str) -> str:
    receipts = {e.evidence_id: e for e in run.evidence}
    grades = {
        receipts[o.evidence_id].grade
        for o in run.observations
        if o.condition_id == condition and o.state == ObservationState.MEASURED
    }
    if not grades:
        return "NOT MEASURED"
    if len(grades) != 1:
        return "mixed (" + ", ".join(sorted(grade.value for grade in grades)) + ")"
    return next(iter(grades)).value


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
    evidence_refs = tuple(
        sorted(
            {
                o.evidence_id
                for o in run.observations
                if o.condition_id == rule.condition_id and o.state == ObservationState.MEASURED
            }
        )
    )
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
        evidence_grade=_grade_for(run, rule.condition_id),
        anchors=rule.anchors,
        evidence_ids=evidence_refs,
        explanation=explanation,
    )


def analyze(run: Run) -> Analysis:
    """Calculate from validated observations only; never impute unknown results."""
    baseline = condition_metrics(run.observations, "baseline")
    candidate = condition_metrics(run.observations, "candidate")
    paired = paired_metrics(run.observations)
    if any(g.passed is False for g in run.gates):
        gate_state = "FAILED - NONCOMPENSATORY"
    elif any(g.passed is None for g in run.gates) or not run.gates:
        gate_state = "UNKNOWN - NOT QUALIFIED"
    else:
        gate_state = "ALL RECORDED GATES PASSED - ADOPTION STILL REQUIRES AUTHORITY"
    return Analysis(
        baseline=baseline,
        candidate=candidate,
        paired=paired,
        criteria=tuple(_criterion(rule, run, baseline, candidate, paired) for rule in run.criteria),
        essential_gate_state=gate_state,
    )
