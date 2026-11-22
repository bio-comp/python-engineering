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


### Noncompensatory acceptance gates

| Gate | Outcome | Requirement / supporting evidence |
| --- | --- | --- |
| G-independent | UNKNOWN | Independent replication; receipts: NONE; No independent or real experimental evidence |
| G-repro | UNKNOWN | Real tool invocation reproduced; receipts: NONE; Simulation does not run a real upstream tool |


### Criterion-level rubric outcomes (no inferred adoption)

| ID / dimension | Metric / scope | Value / n | 0-4 score / evidence |
| --- | --- | --- | --- |
| C-precision: false_positive_burden | precision / candidate | 0.900 / 20 | 3 / synthetic_demonstration; MEASURED |
| C-duration: performance | median_duration_ms / candidate | 11.000 / 65 | 3 / synthetic_demonstration; MEASURED |


### Prespecified 0-4 anchors (scores require actual metrics)

| Criterion | Anchors 0 / 1 / 2 / 3 / 4 |
| --- | --- |
| C-precision | 0: precision < 0.50 \| 1: 0.50 to < 0.70 \| 2: 0.70 to < 0.85 \| 3: 0.85 to < 0.95 \| 4: precision >= 0.95 (requires independent corroboration to qualify) |
| C-duration | 0: median > 80ms \| 1: 40 < median <= 80ms \| 2: 20 < median <= 40ms \| 3: 10 < median <= 20ms \| 4: median <= 10ms; no correctness substitution |


### Raw observation ledger (each finding traces to a receipt)

| Observation / case | Condition / repetition | State | Oracle / outcome | Time ms / evidence |
| --- | --- | --- | --- | --- |
| synthetic-001-baseline / synthetic_case_001 | baseline / 0 / seed=101 | MEASURED | False / False | 8.000 / SYN-001 |
| synthetic-001-candidate / synthetic_case_001 | candidate / 0 / seed=101 | MEASURED | False / False | 6.000 / SYN-001 |
| synthetic-002-baseline / synthetic_case_002 | baseline / 0 / seed=101 | MEASURED | False / False | 9.000 / SYN-001 |
| synthetic-002-candidate / synthetic_case_002 | candidate / 0 / seed=101 | MEASURED | False / False | 7.000 / SYN-001 |
| synthetic-003-baseline / synthetic_case_003 | baseline / 0 / seed=101 | MEASURED | True / True | 10.000 / SYN-001 |
| synthetic-003-candidate / synthetic_case_003 | candidate / 0 / seed=101 | MEASURED | True / True | 8.000 / SYN-001 |
| synthetic-004-baseline / synthetic_case_004 | baseline / 0 / seed=101 | MEASURED | False / False | 11.000 / SYN-001 |
| synthetic-004-candidate / synthetic_case_004 | candidate / 0 / seed=101 | MEASURED | False / False | 9.000 / SYN-001 |
| synthetic-005-baseline / synthetic_case_005 | baseline / 0 / seed=101 | MEASURED | False / False | 12.000 / SYN-001 |
| synthetic-005-candidate / synthetic_case_005 | candidate / 0 / seed=101 | MEASURED | False / False | 10.000 / SYN-001 |
| synthetic-006-baseline / synthetic_case_006 | baseline / 0 / seed=101 | MEASURED | True / True | 13.000 / SYN-001 |
| synthetic-006-candidate / synthetic_case_006 | candidate / 0 / seed=101 | MEASURED | True / True | 11.000 / SYN-001 |
| synthetic-007-baseline / synthetic_case_007 | baseline / 0 / seed=101 | MEASURED | False / False | 14.000 / SYN-001 |
| synthetic-007-candidate / synthetic_case_007 | candidate / 0 / seed=101 | MEASURED | False / False | 12.000 / SYN-001 |
| synthetic-008-baseline / synthetic_case_008 | baseline / 0 / seed=101 | MEASURED | False / False | 15.000 / SYN-001 |
| synthetic-008-candidate / synthetic_case_008 | candidate / 0 / seed=101 | MEASURED | False / False | 13.000 / SYN-001 |
| synthetic-009-baseline / synthetic_case_009 | baseline / 0 / seed=101 | MEASURED | True / True | 16.000 / SYN-001 |
| synthetic-009-candidate / synthetic_case_009 | candidate / 0 / seed=101 | MEASURED | True / True | 14.000 / SYN-001 |
| synthetic-010-baseline / synthetic_case_010 | baseline / 0 / seed=101 | MEASURED | False / False | 17.000 / SYN-001 |
| synthetic-010-candidate / synthetic_case_010 | candidate / 0 / seed=101 | MEASURED | False / False | 15.000 / SYN-001 |
| synthetic-011-baseline / synthetic_case_011 | baseline / 0 / seed=101 | MEASURED | False / False | 18.000 / SYN-001 |
| synthetic-011-candidate / synthetic_case_011 | candidate / 0 / seed=101 | MEASURED | False / False | 16.000 / SYN-001 |
| synthetic-012-baseline / synthetic_case_012 | baseline / 0 / seed=101 | MEASURED | True / True | 19.000 / SYN-001 |
| synthetic-012-candidate / synthetic_case_012 | candidate / 0 / seed=101 | MEASURED | True / True | 17.000 / SYN-001 |
| synthetic-013-baseline / synthetic_case_013 | baseline / 0 / seed=101 | MEASURED | False / False | 7.000 / SYN-001 |
| synthetic-013-candidate / synthetic_case_013 | candidate / 0 / seed=101 | MEASURED | False / False | 5.000 / SYN-001 |
| synthetic-014-baseline / synthetic_case_014 | baseline / 0 / seed=101 | MEASURED | False / False | 8.000 / SYN-001 |
| synthetic-014-candidate / synthetic_case_014 | candidate / 0 / seed=101 | MEASURED | False / False | 6.000 / SYN-001 |
| synthetic-015-baseline / synthetic_case_015 | baseline / 0 / seed=101 | MEASURED | True / False | 9.000 / SYN-001 |
| synthetic-015-candidate / synthetic_case_015 | candidate / 0 / seed=101 | MEASURED | True / True | 7.000 / SYN-001 |
| synthetic-016-baseline / synthetic_case_016 | baseline / 0 / seed=101 | MEASURED | False / False | 10.000 / SYN-001 |
| synthetic-016-candidate / synthetic_case_016 | candidate / 0 / seed=101 | MEASURED | False / False | 8.000 / SYN-001 |
| synthetic-017-baseline / synthetic_case_017 | baseline / 0 / seed=101 | MEASURED | False / True | 11.000 / SYN-001 |
| synthetic-017-candidate / synthetic_case_017 | candidate / 0 / seed=101 | MEASURED | False / False | 9.000 / SYN-001 |
| synthetic-018-baseline / synthetic_case_018 | baseline / 0 / seed=101 | MEASURED | True / True | 12.000 / SYN-001 |
| synthetic-018-candidate / synthetic_case_018 | candidate / 0 / seed=101 | MEASURED | True / True | 10.000 / SYN-001 |
| synthetic-019-baseline / synthetic_case_019 | baseline / 0 / seed=101 | MEASURED | False / False | 13.000 / SYN-001 |
| synthetic-019-candidate / synthetic_case_019 | candidate / 0 / seed=101 | MEASURED | False / False | 11.000 / SYN-001 |
| synthetic-020-baseline / synthetic_case_020 | baseline / 0 / seed=101 | MEASURED | False / False | 14.000 / SYN-001 |
| synthetic-020-candidate / synthetic_case_020 | candidate / 0 / seed=101 | MEASURED | False / False | 12.000 / SYN-001 |
| synthetic-021-baseline / synthetic_case_021 | baseline / 0 / seed=101 | MEASURED | True / True | 15.000 / SYN-001 |
| synthetic-021-candidate / synthetic_case_021 | candidate / 0 / seed=101 | MEASURED | True / False | 13.000 / SYN-001 |
| synthetic-022-baseline / synthetic_case_022 | baseline / 0 / seed=101 | MEASURED | False / False | 16.000 / SYN-001 |
| synthetic-022-candidate / synthetic_case_022 | candidate / 0 / seed=101 | MEASURED | False / False | 14.000 / SYN-001 |
| synthetic-023-baseline / synthetic_case_023 | baseline / 0 / seed=101 | MEASURED | False / False | 17.000 / SYN-001 |
| synthetic-023-candidate / synthetic_case_023 | candidate / 0 / seed=101 | MEASURED | False / False | 15.000 / SYN-001 |
| synthetic-024-baseline / synthetic_case_024 | baseline / 0 / seed=101 | MEASURED | True / True | 18.000 / SYN-001 |
| synthetic-024-candidate / synthetic_case_024 | candidate / 0 / seed=101 | MEASURED | True / True | 16.000 / SYN-001 |
| synthetic-025-baseline / synthetic_case_025 | baseline / 0 / seed=101 | MEASURED | False / False | 19.000 / SYN-001 |
| synthetic-025-candidate / synthetic_case_025 | candidate / 0 / seed=101 | MEASURED | False / False | 17.000 / SYN-001 |
| synthetic-026-baseline / synthetic_case_026 | baseline / 0 / seed=101 | MEASURED | False / False | 7.000 / SYN-001 |
| synthetic-026-candidate / synthetic_case_026 | candidate / 0 / seed=101 | MEASURED | False / False | 5.000 / SYN-001 |
| synthetic-027-baseline / synthetic_case_027 | baseline / 0 / seed=101 | MEASURED | True / True | 8.000 / SYN-001 |
| synthetic-027-candidate / synthetic_case_027 | candidate / 0 / seed=101 | MEASURED | True / True | 6.000 / SYN-001 |
| synthetic-028-baseline / synthetic_case_028 | baseline / 0 / seed=101 | MEASURED | False / False | 9.000 / SYN-001 |
| synthetic-028-candidate / synthetic_case_028 | candidate / 0 / seed=101 | MEASURED | False / False | 7.000 / SYN-001 |
| synthetic-029-baseline / synthetic_case_029 | baseline / 0 / seed=101 | MEASURED | False / False | 10.000 / SYN-001 |
| synthetic-029-candidate / synthetic_case_029 | candidate / 0 / seed=101 | MEASURED | False / True | 8.000 / SYN-001 |
| synthetic-030-baseline / synthetic_case_030 | baseline / 0 / seed=101 | MEASURED | True / False | 11.000 / SYN-001 |
| synthetic-030-candidate / synthetic_case_030 | candidate / 0 / seed=101 | MEASURED | True / True | 9.000 / SYN-001 |
| synthetic-031-baseline / synthetic_case_031 | baseline / 0 / seed=101 | MEASURED | False / False | 12.000 / SYN-001 |
| synthetic-031-candidate / synthetic_case_031 | candidate / 0 / seed=101 | MEASURED | False / False | 10.000 / SYN-001 |
| synthetic-032-baseline / synthetic_case_032 | baseline / 0 / seed=101 | MEASURED | False / False | 13.000 / SYN-001 |
| synthetic-032-candidate / synthetic_case_032 | candidate / 0 / seed=101 | MEASURED | False / False | 11.000 / SYN-001 |
| synthetic-033-baseline / synthetic_case_033 | baseline / 0 / seed=101 | MEASURED | True / True | 14.000 / SYN-001 |
| synthetic-033-candidate / synthetic_case_033 | candidate / 0 / seed=101 | MEASURED | True / True | 12.000 / SYN-001 |
| synthetic-034-baseline / synthetic_case_034 | baseline / 0 / seed=101 | MEASURED | False / True | 15.000 / SYN-001 |
| synthetic-034-candidate / synthetic_case_034 | candidate / 0 / seed=101 | MEASURED | False / False | 13.000 / SYN-001 |
| synthetic-035-baseline / synthetic_case_035 | baseline / 0 / seed=101 | MEASURED | False / False | 16.000 / SYN-001 |
| synthetic-035-candidate / synthetic_case_035 | candidate / 0 / seed=101 | MEASURED | False / False | 14.000 / SYN-001 |
| synthetic-036-baseline / synthetic_case_036 | baseline / 0 / seed=101 | MEASURED | True / True | 17.000 / SYN-001 |
| synthetic-036-candidate / synthetic_case_036 | candidate / 0 / seed=101 | MEASURED | True / True | 15.000 / SYN-001 |
| synthetic-037-baseline / synthetic_case_037 | baseline / 0 / seed=101 | MEASURED | False / False | 18.000 / SYN-001 |
| synthetic-037-candidate / synthetic_case_037 | candidate / 0 / seed=101 | MEASURED | False / False | 16.000 / SYN-001 |
| synthetic-038-baseline / synthetic_case_038 | baseline / 0 / seed=101 | MEASURED | False / False | 19.000 / SYN-001 |
| synthetic-038-candidate / synthetic_case_038 | candidate / 0 / seed=101 | MEASURED | False / False | 17.000 / SYN-001 |
| synthetic-039-baseline / synthetic_case_039 | baseline / 0 / seed=101 | MEASURED | True / True | 7.000 / SYN-001 |
| synthetic-039-candidate / synthetic_case_039 | candidate / 0 / seed=101 | MEASURED | True / True | 5.000 / SYN-001 |
| synthetic-040-baseline / synthetic_case_040 | baseline / 0 / seed=101 | MEASURED | False / False | 8.000 / SYN-001 |
| synthetic-040-candidate / synthetic_case_040 | candidate / 0 / seed=101 | MEASURED | False / False | 6.000 / SYN-001 |
| synthetic-041-baseline / synthetic_case_041 | baseline / 0 / seed=101 | MEASURED | False / False | 9.000 / SYN-001 |
| synthetic-041-candidate / synthetic_case_041 | candidate / 0 / seed=101 | MEASURED | False / False | 7.000 / SYN-001 |
| synthetic-042-baseline / synthetic_case_042 | baseline / 0 / seed=101 | MEASURED | True / True | 10.000 / SYN-001 |
| synthetic-042-candidate / synthetic_case_042 | candidate / 0 / seed=101 | MEASURED | True / False | 8.000 / SYN-001 |
| synthetic-043-baseline / synthetic_case_043 | baseline / 0 / seed=101 | MEASURED | False / False | 11.000 / SYN-001 |
| synthetic-043-candidate / synthetic_case_043 | candidate / 0 / seed=101 | MEASURED | False / False | 9.000 / SYN-001 |
| synthetic-044-baseline / synthetic_case_044 | baseline / 0 / seed=101 | MEASURED | False / False | 12.000 / SYN-001 |
| synthetic-044-candidate / synthetic_case_044 | candidate / 0 / seed=101 | MEASURED | False / False | 10.000 / SYN-001 |
| synthetic-045-baseline / synthetic_case_045 | baseline / 0 / seed=101 | MEASURED | True / False | 13.000 / SYN-001 |
| synthetic-045-candidate / synthetic_case_045 | candidate / 0 / seed=101 | MEASURED | True / True | 11.000 / SYN-001 |
| synthetic-046-baseline / synthetic_case_046 | baseline / 0 / seed=101 | MEASURED | False / False | 14.000 / SYN-001 |
| synthetic-046-candidate / synthetic_case_046 | candidate / 0 / seed=101 | MEASURED | False / False | 12.000 / SYN-001 |
| synthetic-047-baseline / synthetic_case_047 | baseline / 0 / seed=101 | MEASURED | False / False | 15.000 / SYN-001 |
| synthetic-047-candidate / synthetic_case_047 | candidate / 0 / seed=101 | MEASURED | False / False | 13.000 / SYN-001 |
| synthetic-048-baseline / synthetic_case_048 | baseline / 0 / seed=101 | MEASURED | True / True | 16.000 / SYN-001 |
| synthetic-048-candidate / synthetic_case_048 | candidate / 0 / seed=101 | MEASURED | True / True | 14.000 / SYN-001 |
| synthetic-049-baseline / synthetic_case_049 | baseline / 0 / seed=101 | MEASURED | False / False | 17.000 / SYN-001 |
| synthetic-049-candidate / synthetic_case_049 | candidate / 0 / seed=101 | MEASURED | False / False | 15.000 / SYN-001 |
| synthetic-050-baseline / synthetic_case_050 | baseline / 0 / seed=101 | MEASURED | False / False | 18.000 / SYN-001 |
| synthetic-050-candidate / synthetic_case_050 | candidate / 0 / seed=101 | MEASURED | False / False | 16.000 / SYN-001 |
| synthetic-051-baseline / synthetic_case_051 | baseline / 0 / seed=101 | MEASURED | True / True | 19.000 / SYN-001 |
| synthetic-051-candidate / synthetic_case_051 | candidate / 0 / seed=101 | MEASURED | True / True | 17.000 / SYN-001 |
| synthetic-052-baseline / synthetic_case_052 | baseline / 0 / seed=101 | MEASURED | False / False | 7.000 / SYN-001 |
| synthetic-052-candidate / synthetic_case_052 | candidate / 0 / seed=101 | MEASURED | False / False | 5.000 / SYN-001 |
| synthetic-053-baseline / synthetic_case_053 | baseline / 0 / seed=101 | MEASURED | False / False | 8.000 / SYN-001 |
| synthetic-053-candidate / synthetic_case_053 | candidate / 0 / seed=101 | MEASURED | False / False | 6.000 / SYN-001 |
| synthetic-054-baseline / synthetic_case_054 | baseline / 0 / seed=101 | MEASURED | True / True | 9.000 / SYN-001 |
| synthetic-054-candidate / synthetic_case_054 | candidate / 0 / seed=101 | MEASURED | True / True | 7.000 / SYN-001 |
| synthetic-055-baseline / synthetic_case_055 | baseline / 0 / seed=101 | MEASURED | False / False | 10.000 / SYN-001 |
| synthetic-055-candidate / synthetic_case_055 | candidate / 0 / seed=101 | MEASURED | False / False | 8.000 / SYN-001 |
| synthetic-056-baseline / synthetic_case_056 | baseline / 0 / seed=101 | MEASURED | False / False | 11.000 / SYN-001 |
| synthetic-056-candidate / synthetic_case_056 | candidate / 0 / seed=101 | MEASURED | False / False | 9.000 / SYN-001 |
| synthetic-057-baseline / synthetic_case_057 | baseline / 0 / seed=101 | MEASURED | True / True | 12.000 / SYN-001 |
| synthetic-057-candidate / synthetic_case_057 | candidate / 0 / seed=101 | MEASURED | True / True | 10.000 / SYN-001 |
| synthetic-058-baseline / synthetic_case_058 | baseline / 0 / seed=101 | MEASURED | False / False | 13.000 / SYN-001 |
| synthetic-058-candidate / synthetic_case_058 | candidate / 0 / seed=101 | MEASURED | False / True | 11.000 / SYN-001 |
| synthetic-059-baseline / synthetic_case_059 | baseline / 0 / seed=101 | MEASURED | False / False | 14.000 / SYN-001 |
| synthetic-059-candidate / synthetic_case_059 | candidate / 0 / seed=101 | MEASURED | False / False | 12.000 / SYN-001 |
| synthetic-060-baseline / synthetic_case_060 | baseline / 0 / seed=101 | MEASURED | True / False | 15.000 / SYN-001 |
| synthetic-060-candidate / synthetic_case_060 | candidate / 0 / seed=101 | MEASURED | True / True | 13.000 / SYN-001 |
| synthetic-061-baseline / synthetic_case_061 | baseline / 0 / seed=101 | MEASURED | False / False | 16.000 / SYN-001 |
| synthetic-061-candidate / synthetic_case_061 | candidate / 0 / seed=101 | MEASURED | False / False | 14.000 / SYN-001 |
| synthetic-062-baseline / synthetic_case_062 | baseline / 0 / seed=101 | MEASURED | False / False | 17.000 / SYN-001 |
| synthetic-062-candidate / synthetic_case_062 | candidate / 0 / seed=101 | MEASURED | False / False | 15.000 / SYN-001 |
| synthetic-063-baseline / synthetic_case_063 | baseline / 0 / seed=101 | MEASURED | True / True | 18.000 / SYN-001 |
| synthetic-063-candidate / synthetic_case_063 | candidate / 0 / seed=101 | MEASURED | True / False | 16.000 / SYN-001 |
| synthetic-064-baseline / synthetic_case_064 | baseline / 0 / seed=101 | MEASURED | False / False | 19.000 / SYN-001 |
| synthetic-064-candidate / synthetic_case_064 | candidate / 0 / seed=101 | MEASURED | False / False | 17.000 / SYN-001 |
| synthetic-065-baseline / synthetic_case_065 | baseline / 0 / seed=101 | MEASURED | False / False | 7.000 / SYN-001 |
| synthetic-065-candidate / synthetic_case_065 | candidate / 0 / seed=101 | MEASURED | False / False | 5.000 / SYN-001 |


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
| Raw measurements | SYNTHETIC | Measured rows: 130 |
| Paired baseline/candidate | PRESENT | Matched case/repetition/seed pairs: 65 |
| Prespecified anchored scoring | PRESENT | No composite score is inferred |
| False positive and negative review | PRESENT | Requires independently labeled representative corpus to generalize |
| Noncompensatory gates | UNKNOWN - NOT QUALIFIED | Missing/failed gates override any favorable score |
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
