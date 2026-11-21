# Synthetic analyzer comparison and table-stress demonstration

**SYNTHETIC DEMONSTRATION - NOT EMPIRICAL TOOL EVIDENCE**

Experiment **E-900** / protocol **SYNTHETIC-NOT-REGISTERED-v1** / run **synthetic-stress-v1**

Execution: **2026-11-17T23:32:41.189679+00:00** | Study status: **PILOT**

**Question:** Can the reporting harness preserve synthetic evidence labels and uncertainty?

**Hypothesis:** Unknown results remain unscored and synthetic measurements never imply efficacy.

**Prespecified decision criteria:** Check validation, tables, evidence-grade, score threshold boundaries and gates.

**Source-reported interpretation:** Artificial run used exclusively to verify the reporting implementation.

**Essential gates:** UNKNOWN - NOT QUALIFIED

**Disposition (recorded, not generated):** NO ADOPTION DECISION - SYNTHETIC DEMO

**Applicability:** PDF/Markdown renderer, validation, page flow, missing evidence and score mechanics only

**Statistical scope:** Descriptive counts, proportions, and medians only; no confidence intervals/p-values without an independently specified sampling design.

## Key measured results

### Measured outcomes: distinct condition-level observations

| Metric / denominator | Baseline | Candidate |
| --- | --- | --- |
| Recorded observation rows | 65 | 65 |
| Measured rows | 65 | 65 |
| Diagnostic rows | 65 | 65 |
| True positives | 17 | 18 |
| False positives | 2 | 2 |
| True negatives | 42 | 42 |
| False negatives | 4 | 3 |
| Precision | 0.895 | 0.900 |
| Recall | 0.810 | 0.857 |
| Specificity | 0.955 | 0.955 |
| Accuracy | 0.908 | 0.923 |
| Duration observations | 65 | 65 |
| Median duration (ms) | 13.000 | 11.000 |

### Paired evidence (description, not an IID inferential claim)

| Measure | Observed |
| --- | --- |
| Matched case/repetition/seed pairs | 65 |
| Baseline-only correct | 5 |
| Candidate-only correct | 6 |
| Both correct | 54 |
| Both wrong | 0 |
| Candidate - baseline accuracy | 0.015 |
| Candidate-only true-positive detections | 4 |

## Limitations

- All observed numbers and defect labels are generated, not tool measurements.
- Repeated or paired rows are synthetic; no generalization or statistical inference.
- Upstream identity is intentionally fictional and nonqualified.

**Next qualification step:** Independent review and real frozen protocol-scoped experimental run.
