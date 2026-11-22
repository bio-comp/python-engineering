# Synthetic reporting abstention demonstration

**SYNTHETIC DEMONSTRATION - NOT EMPIRICAL TOOL EVIDENCE**

Experiment **E-901** / protocol **SYNTHETIC-NOT-REGISTERED-v1** / run **synthetic-blocked-v1**

Execution: **2026-11-17T23:32:41.229502+00:00** | Study status: **BLOCKED**

**Question:** Can the reporting harness preserve synthetic evidence labels and uncertainty?

**Hypothesis:** Unknown results remain unscored and synthetic measurements never imply efficacy.

**Prespecified decision criteria:** Check validation, tables, evidence-grade, score threshold boundaries and gates.

**Source-reported interpretation:** Artificial run used exclusively to verify the reporting implementation.

**Essential gates:** FAILED - NONCOMPENSATORY

**Disposition (recorded, not generated):** NO ADOPTION DECISION - SYNTHETIC DEMO

**Applicability:** PDF/Markdown renderer, validation, page flow, missing evidence and score mechanics only

**Statistical scope:** Descriptive counts, proportions, and medians only; no confidence intervals/p-values without an independently specified sampling design.

## Key measured results

### Measured outcomes: distinct condition-level observations

| Metric / denominator | Baseline | Candidate |
| --- | --- | --- |
| Recorded observation rows | 0 | 1 |
| Measured rows | 0 | 0 |
| Diagnostic rows | 0 | 0 |
| True positives | 0 | 0 |
| False positives | 0 | 0 |
| True negatives | 0 | 0 |
| False negatives | 0 | 0 |
| Precision | NOT MEASURED | NOT MEASURED |
| Recall | NOT MEASURED | NOT MEASURED |
| Specificity | NOT MEASURED | NOT MEASURED |
| Accuracy | NOT MEASURED | NOT MEASURED |
| Duration observations | 0 | 0 |
| Median duration (ms) | NOT MEASURED | NOT MEASURED |

### Paired evidence (description, not an IID inferential claim)

| Measure | Observed |
| --- | --- |
| Matched case/repetition/seed pairs | 0 |
| Baseline-only correct | 0 |
| Candidate-only correct | 0 |
| Both correct | 0 |
| Both wrong | 0 |
| Candidate - baseline accuracy | NOT MEASURED |
| Candidate-only true-positive detections | 0 |

## Limitations

- All observed numbers and defect labels are generated, not tool measurements.
- Repeated or paired rows are synthetic; no generalization or statistical inference.
- Upstream identity is intentionally fictional and nonqualified.

**Next qualification step:** Independent review and real frozen protocol-scoped experimental run.

## Complete evidence and reproducibility record

### Exact experimental conditions

| Aspect | Baseline | Candidate |
| --- | --- | --- |
| Tool identity | FictionalAnalyzer | FictionalAnalyzer |
| Version | 0.0.0 | 0.0.0-fictional |
| Configuration | synthetic test default | synthetic aggressive flags |


### Observed execution provenance

| Attribute | Exact value |
| --- | --- |
| Python | CPython 3.14.10 |
| Interpreter executable | /Users/mikeh/repos/python-engineering-reporting/.venv/bin/python3 |
| uv | uv 0.8.4 (e176e1714 2025-07-30) |
| Operating system | Darwin 25.6.0 (arm64) |
| Runtime / CI runner | isolated macOS worktree; captured before publication; the Git source checkout may be dirty; NOT APPLICABLE |
| Repository / branch | git@github.com:bio-comp/python-engineering.git / feat/issue18-reporting-foundation |
| Git commit | a4d85dc42229f2425216a591303847de47facc0d |
| Fixture revision | synthetic-generator-v1 |
| Lockfile SHA-256 | e8e893ac9dc30f38e7b20d5c0376b6c3a8eda4341bf0004015ec860ca4ffab5d |
| pyproject.toml SHA-256 | b74deb779a140dedb546415bf6c8a99dcfa2ebac11c42f59b3e5e27873c4f386 |
| Harness / generator | synthetic-generator-v1 / 0.1.0 |
| Tool versions | SyntheticAnalyzer=0.0.0-fictional |
| Dependencies | pydantic=2.14.1; reportlab=4.5.1 |
| Hardware | NOT MEASURED |
| Selected environment | NOT MEASURED |
| Seeds | 101 |
| Model / permissions | NOT APPLICABLE; NOT APPLICABLE |
| Prompt revision | NOT APPLICABLE |
| Source retrieval time | 2026-11-17 (renderer documentation; exact retrieval timestamp unavailable) |


### Measured outcomes: distinct condition-level observations

| Metric / denominator | Baseline | Candidate |
| --- | --- | --- |
| Recorded observation rows | 0 | 1 |
| Measured rows | 0 | 0 |
| Diagnostic rows | 0 | 0 |
| True positives | 0 | 0 |
| False positives | 0 | 0 |
| True negatives | 0 | 0 |
| False negatives | 0 | 0 |
| Precision | NOT MEASURED | NOT MEASURED |
| Recall | NOT MEASURED | NOT MEASURED |
| Specificity | NOT MEASURED | NOT MEASURED |
| Accuracy | NOT MEASURED | NOT MEASURED |
| Duration observations | 0 | 0 |
| Median duration (ms) | NOT MEASURED | NOT MEASURED |


### Paired evidence (description, not an IID inferential claim)

| Measure | Observed |
| --- | --- |
| Matched case/repetition/seed pairs | 0 |
| Baseline-only correct | 0 |
| Candidate-only correct | 0 |
| Both correct | 0 |
| Both wrong | 0 |
| Candidate - baseline accuracy | NOT MEASURED |
| Candidate-only true-positive detections | 0 |


### Noncompensatory acceptance gates

| Gate | Outcome | Requirement / supporting evidence |
| --- | --- | --- |
| G-independent | UNKNOWN | Independent replication; receipts: NONE; No independent or real experimental evidence |
| G-repro | FAIL | Real tool invocation reproduced; receipts: NONE; Simulation does not run a real upstream tool |


### Criterion-level rubric outcomes (no inferred adoption)

| ID / dimension | Metric / scope | Value / n | 0-4 score / evidence |
| --- | --- | --- | --- |
| C-precision: false_positive_burden | precision / candidate | NOT MEASURED / 0 | NOT MEASURED / NOT MEASURED; INSUFFICIENT EVIDENCE |
| C-duration: performance | median_duration_ms / candidate | NOT MEASURED / 0 | NOT MEASURED / NOT MEASURED; INSUFFICIENT EVIDENCE |


### Prespecified 0-4 anchors (scores require actual metrics)

| Criterion | Anchors 0 / 1 / 2 / 3 / 4 |
| --- | --- |
| C-precision | 0: precision < 0.50 \| 1: 0.50 to < 0.70 \| 2: 0.70 to < 0.85 \| 3: 0.85 to < 0.95 \| 4: precision >= 0.95 (requires independent corroboration to qualify) |
| C-duration | 0: median > 80ms \| 1: 40 < median <= 80ms \| 2: 20 < median <= 40ms \| 3: 10 < median <= 20ms \| 4: median <= 10ms; no correctness substitution |


### Raw observation ledger (each finding traces to a receipt)

| Observation / case | Condition / repetition | State | Oracle / outcome | Time ms / evidence |
| --- | --- | --- | --- | --- |
| blocked-001 / unexecuted_case_001 | candidate / 0 / seed=None | EXECUTION BLOCKED | None / None | NOT MEASURED / SYN-001 |


### Evidence receipts and independent/source strength

| Receipt | Strength | Identity / locator / note |
| --- | --- | --- |
| SYN-001 | synthetic_demonstration | examples/build_demo_inputs.py; make_run / generated controlled pseudodata; Constructed synthetic rows are purposely not real analyzer observations. Long wrapped explanatory notes exercise PDF page and table layout and prevent a green-looking report from masquerading as independently verified evidence. Every result is synthetic and must be excluded from adoption decisions. |
| DOC-001 | documentation_only | https://docs.reportlab.com/reportlab/userguide/ch7_tables/; Tables and TableStyles / repeatRows; Official renderer capability documentation; not an observation or tool efficacy oracle. |


### Standard experimental evidence checklist

| Control | Assessment | Scope / caveat |
| --- | --- | --- |
| Protocol and hypotheses | DECLARED | Identity, revision and prespecified criteria are provided; provenance must be audited |
| Execution provenance | DECLARED | Interpreter, exact versions, hashes, commands, branch and commit supplied; not externally attested |
| Raw measurements | SYNTHETIC | Measured rows: 0 |
| Paired baseline/candidate | INSUFFICIENT | Matched case/repetition/seed pairs: 0 |
| Prespecified anchored scoring | PRESENT | No composite score is inferred |
| False positive and negative review | NOT MEASURED | Requires independently labeled representative corpus to generalize |
| Noncompensatory gates | FAILED - NONCOMPENSATORY | Missing/failed gates override any favorable score |
| Independent reproduction | NOT MEASURED | Local synthetic checks do not establish efficacy |
| Interpretation / limitations | DECLARED | Human-supplied interpretation remains a snapshot, not a Drive decision |
| Report reproducibility | GENERATED | Inspect manifest.json SHA-256 entries; printed reports are versioned snapshots |


### Exact reproduction commands as recorded by the run

| Sequence | Command |
| --- | --- |
| 1 | uv run --locked python examples/build_demo_inputs.py |
| 2 | uv run --locked python -m python_engineering.reporting build-report examples/synthetic_900.json reports/E-900/synthetic-stress-v1 |


## Reproduction and governance boundary

Reporting generator: 0.1.0; rubric revision: synthetic-demo-rubric-v1; schema 1.0.

The run JSON is the frozen input. This report is a generated snapshot, not the Google Drive research canonical.

A passing gate alone cannot authorize tool adoption; false-positive, generalization, and independent-review requirements remain.
