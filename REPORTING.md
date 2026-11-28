# Python Engineering — Scientific Reporting Contract (v0.2 correction proposal)

**Authority:** Google Drive Python Engineering canonicals retain protocol, research state, interpretation, source qualification, recipes, and adoption decisions. This repository owns executable code, isolated fixtures, tests, and immutable run evidence. The report is a versioned evidence **snapshot**, not an alternative canonical.

## Common artifact schema

`Run` is the strict, frozen Pydantic v2 boundary (`schema_version=1.0`) that combines an experiment identity, conditions, environment, raw observations, evidence receipts, anchored criteria, essential gates, and *source-recorded* interpretation. It separates four information layers: untouched `run.json`, computed `analysis.json`, human-supplied interpretation, and the independent Drive adoption authority. Source-reported status/grade/gate assertions are **not externally attested** by this generator.

The schema includes the experiment ID, protocol revision, unique run ID, timezone-aware execution time, hypothesis and prespecified criteria, exact baseline/candidate identity, configuration, source commit, execution commands, full Python/uv/tool versions, lockfile/`pyproject.toml` SHA-256, OS/arch/CI/runtime, hardware where applicable, seeds, agent/model identifiers where applicable, and evidence source/locator/receipt SHA-256. A value of `NOT MEASURED`, `NOT APPLICABLE`, `INSUFFICIENT EVIDENCE`, or `EXECUTION BLOCKED` is never coerced to numeric zero. Reject malformed, duplicate, missing-reference, and inconsistent inputs.

Binary defect and duration measurements are supported. Additional heterogeneous result families, rich scanner diagnostics, verified source attestation, and agent cost telemetry require versioned extensions; do not claim they exist based on a scorecard heading.

## Rubric proposal

Each criterion provides a category, dimension, precise question, computed metric, measurement direction, four **prespecified strictly ordered thresholds**, five concrete observable anchors, minimum denominator, and required flag. Anchors 0–4 have these general semantics:

| Score | Observable meaning |
| ---: | --- |
| 0 | Measured failure or unacceptable performance against the criterion |
| 1 | Substantial deficiencies against a prespecified threshold |
| 2 | Mixed/partial value at the next boundary |
| 3 | Meets the prespecified requirement under the evaluated conditions |
| 4 | Strong numerical result at strictest boundary, **not** automatically strong evidence |

The score is determined mechanically: compare the measured metric with the four thresholds; apply higher-is-better or lower-is-better as defined. If sample size or metric is inadequate, abstain. **Evidence strength is separate:** independently reproduced, controlled local, small pilot, documentation only, anecdotal, or synthetic demonstration. A grade entered into the JSON is a claim to be independently audited, not an automatically certified source receipt.

**Noncompensatory:** any essential gate that is false forces `FAILED - NONCOMPENSATORY`; unknown/no recorded gates means `UNKNOWN - NOT QUALIFIED`; all recorded passes never themselves authorize adoption. No composite scores or weighted rankings in v0.1. A future composite requires prespecified utilities/weights, adequate coverage, sensitivity analysis, metric comparability, and governed adoption authorization.

### Category-specific scorecards

`CATEGORY_PROFILES` documents seven classes (category questions, not preselected thresholds or adoption policy):

| Category | Key questions and gate examples |
| --- | --- |
| Static analysis and typing | True *unique* catches beyond Ruff/mypy; labeled false positives; version/Pydantic compatibility; diagnostic quality; unsafe semantic fix gate |
| pre-commit/prek/native/CI | Same underlying checks, staged-file correctness, failure propagation, cold/warm cost; false-green gate |
| Durable workflow orchestration | Retries, crash/restart, idempotency, durable state and operational burden; lost job/duplicate side-effect gate |
| Wheel/lockfile compatibility | Target ABI/tags/architecture, artifact availability, false assurances; deployment false-green gate |
| Profiling | Tracing signal, perturbation, overhead and async completeness; changed functional output gate |
| Citation/source verification | Reference existence, metadata, publication/retraction status, document identity, **actual source-to-claim support**; metadata is not claim support |
| Coding-agent retrieval | Oracle-verified task outcomes, false claims, API/version evidence, rounds, cost and latency, regressions; unverified permissions gate |

## Statistics and comparisons

Implemented: TP/FP/TN/FN, exact denominators, precision/recall/specificity/accuracy, median duration, matched condition differences, discordant correctness counts and candidate-only positive detections. Pairing requires equal `(case_id, repetition, seed)` and consistent reference oracle. Missing denominators return null; Markdown/PDF show `NOT MEASURED`. Full-precision arithmetic precedes display rounding.

**No automatic p-values, confidence intervals, bootstraps, population efficacy claims, multiple-comparison correction, or causal interpretation.** The synthetic fixture does not establish independent task observations. `compare-runs` rejects different experiment IDs/protocol revisions/rubric revisions/conditions but does **not** certify exchangeable task populations. Inferential-methodology decisions belong to the relevant authoritative protocol / `llm_evaluation`.

## Report and PDF specification

Every output comes from one validated `Run` and shared derived `Analysis` and `TableSpec` objects.

**PDF page 1:** title, experiment/run/version/date/status, source-reported interpretation/disposition, gate status, limitations, and baseline/candidate result table. **Page 2:** hypothesis/design/criteria and exact provenance matrices. **Subsequent pages:** paired data, gates, individual rubric scores and anchors, raw per-case evidence, source references, a standardized experiment checklist, reproduction commands, and explicit boundaries.

For tables: ReportLab 4.5.1 `LongTable`, fixed column proportions, wrapped selectable text, repeating headers, considered row separation, subdued banding, precise units, PDF links, page numbering, rubric version and consistent precision. The build deliberately exercises a 130-row multipage table and long wrapped evidence strings. Official tables reference: https://docs.reportlab.com/reportlab/userguide/ch7_tables/.

**PDF renderer decision is provisional engineering judgment.** ReportLab enables a Python-only table/pagination implementation with deterministic output tested here. Typst (https://typst.app/docs/) offers typesetting, but adds an external toolchain; WeasyPrint (https://doc.courtbouillon.org/weasyprint/) offers CSS-driven layouts with additional runtime/font dependencies. This project has **not** completed controlled comparative benchmarks of renderers. Unicode/font coverage, accessibility audits, vector plotting, landscape layouts and unusual long-token stress remain unqualified.

## Reproducible commands

From the exact repository checkout, after `uv python install 3.14.10` and `uv sync --locked`:

```bash
uv run --locked python -m python_engineering.reporting validate-run examples/synthetic_900.json
uv run --locked python -m python_engineering.reporting score-run examples/synthetic_900.json
uv run --locked python -m python_engineering.reporting compare-runs \
    examples/synthetic_900.json examples/synthetic_900.json
uv run --locked python -m python_engineering.reporting build-report \
    examples/synthetic_900.json /tmp/pyeng-e900-regenerated
uv run --locked python -c 'from python_engineering.reporting.models import Run; print(Run.model_json_schema())'
```

`build-report` requires a **new, nonexistent** output directory and never silently overwrites observations. Bundle: `run.json` (original bytes), `analysis.json`, `summary.md`, `report.md`, `report.pdf`, `manifest.json` (SHA-256 for each artifact, input, rubric/schema/generator version and source-commit identity).

`examples/synthetic_900.json` (130 synthetic recorded observations) and `examples/synthetic_901.json` (blocked, unmeasured) are explicitly **not real tool experiments**; `E-900/E-901` are reserved only for demonstrator fixtures, not Drive-registered experimental IDs. Regenerating the synthetic source generator produces a *new execution timestamp*; regenerate a byte-identical report from the already frozen `run.json` instead. Automated PDF invariance and text/pagination/link tests guard reproducibility.

Core verification (repository's existing quality gates; no weakening):

```bash
uv lock --check
uv run --locked ruff check --no-fix .
uv run --locked ruff format --check .
uv run --locked mypy src tests
uv run --locked pytest --randomly-seed=101 --cov=python_engineering --cov-branch --cov-report=term-missing -q
uv build
```

The user-provided source, tool versions, commands and external evidence should be independently confirmed before publication; credential-pattern checks reduce but do not eliminate disclosure risk.

## Qualification boundaries and follow-up

**Implemented:** strict schema validation, binary/duration/pair descriptive scoring, gate precedence, category prompts, deterministic Markdown/PDF, searchable wrapped multipage tables, immutable hashes and frozen synthetic demo. **Not qualified/implemented:** independent empirical tool comparison, precise calibrated evidence grades, trusted/attested environment capture, statistics beyond descriptive metrics, composite ranking, broad heterogeneous telemetry, real E-001/E-005/E-010/E-011/E-013/E-014/E-015 imports, or a marimo viewer. There is no measured multi-run dataset yet that warrants a marimo interface.

**Canonical reconciliation proposal only — no Drive writes:** after independent code review, register this *reporting implementation status* as an artifact cross-reference in `EXPERIMENTS.md` and a proposed reproducible workflow in `RECIPES.md`; qualify renderer source and applicability in `SOURCE_INDEX.md` after independent assessment. Do not change any tool lifecycle/`CURRENT_PRACTICES.md` or treat an unreviewed report as a decision. A future accepted reporting policy would require an explicit `DECISIONS.md` entry.

**Next step:** publish draft PR; independent Code Review & Quality on a pinned head and base; address findings in the same PR; separately seek merge authorization. Protected application repositories and installed skills remain untouched.

## R1 correction contract — reporting generator 0.2.0

**Compatibility:** Structural input JSON schema remains `1.0` with stronger Python-level semantic validation. The R3 report generator was `0.2.2` (empirical-support and PDF glyph-zero/footer corrections). Original synthetic E-900/E-901 inputs, PDFs and SHA-256 manifests generated by `0.1.0` remain frozen and untouched. New reports belong in distinct output directories.

**R1 — long tables and atomicity.** ReportLab `LongTable(splitInRow=1)` can split large wrapped evidence cells across pages rather than truncating or failing. Test fixtures include 4,000 and 12,000 characters. Publication happens only after the JSON, Markdown, PDF and manifest have been generated in an unpublished sibling staging directory; a directory rename publishes the complete bundle. Failed builds clean staging; existing successful bundles are not overwritten. Network or hostile concurrent filesystem writes are not an endorsed deployment model.

**R2 — run comparison.** Descriptive performance comparisons require identical experiment ID/protocol, baseline and candidate definitions, rubric, fixture revision, synthetic state and complete observation population keyed by `(condition_id, case_id, repetition, seed)`, including identical measurement states and reference truth. Changed predictions may be compared. Missing, added or changed cases/oracles are rejected by default, with no misleading performance delta.

**R3 — stable reference oracle.** `case_id` denotes a fixture with one independent oracle truth across all conditions, repetitions and seeds. Distinct seeded fixture/truth requires a distinct case ID. `validate-run` rejects contradictory expected labels. The source model is the single invariant authority; analyses rely on validated input.

**R4 — required criteria.** The report separately discloses recorded noncompensatory gates, required-criterion completeness, and overall *recorded evidence readiness*. A required criterion without a computable score is incomplete even if all recorded gates pass. An optional unscored criterion does not block an otherwise complete required set. No observed result alone authorizes research qualification or tool adoption.

**R5 — source receipt verification.** A supplied SHA-256 is **declared** until explicitly checked. `validate-run --evidence-root <root>` and `build-report --evidence-root <root>` verify only relative non-symlinked local files within that authorized root. A mismatched digest or unsafe path fails closed; unavailable files and external URLs remain explicitly `UNVERIFIED`. No arbitrary URL download occurs. New bundles include `evidence_verification.json` plus per-file hashes in the manifest. Verified local bytes are not independently attested scientific reproduction. This is a local integrity check, not a secure filesystem sandbox against concurrent hostile actors.

**R6 — Unicode repertoire.** The default PDF renderer embeds ReportLab's bundled Bitstream Vera TrueType font, checking every displayed character against that font's actual cmap. Unsupported glyphs cause an explicit exception before publication, never an unmarked square. For broader Greek/Cyrillic/CJK, provide `build-report --font <approved.ttf>`; the font basename and SHA-256 are recorded in the manifest without distributing font bytes. Supported characters remain selectable. The tested font selection is not general multilingual/emoji/accessibility qualification. The example rocket emoji is unsupported by the tested fonts and is rejected explicitly.

**R7 — independent evidence attribution.** Only evidence grades attached to actual measured observations are considered. A disconnected receipt or zero observations never establishes independent reproduction. Linked independent-grade receipts are labeled `SOURCE DECLARED - NOT ATTESTED`, and mixed grades are labeled accordingly. Scientific replication still requires independently verified provenance.

### Reproduce the corrected pipeline

```bash
uv run --locked python -m python_engineering.reporting validate-run \
    examples/synthetic_900.json --evidence-root .
uv run --locked python -m python_engineering.reporting build-report \
    examples/synthetic_900.json /tmp/pyeng-new-version-report --evidence-root .
uv run --locked python -m python_engineering.reporting compare-runs \
    examples/synthetic_900.json examples/synthetic_900.json
```

The checked-in `examples/reporting.schema.json` represents structural schema `1.0` (with the backward-compatible optional replay-manifest extension below); Python validators and explicit receipt verification implement additional semantic invariants. The R1 known-bad regression corpus is `tests/test_reporting_r1.py`. The generator remains a proposed tool pending independent R2 review and explicit integration authorization.

### R2 correction record — synthetic classification, score provenance and PDF metadata

**R2-F1 — measured-evidence provenance.** Effective classification is derived from evidence grades linked to measured observations, not from the input synthetic-demonstration boolean alone. Distinct states are synthetic-only measured evidence; mixed synthetic and nonsynthetic source declarations; nonsynthetic source declarations (not independently attested); and no measured evidence. Synthetic-linked measured rows require the input synthetic-demonstration flag to be true; a contradiction is rejected at validation. Mixed measured evidence cannot become qualified merely because all recorded gates pass. The classification flows into analysis, Markdown, PDF and the new manifest. The original 0.1.0 bundles remain frozen and unchanged.

**R2-F2 — metric-specific support.** Each criterion records exact contributing observation IDs and receipt IDs. Precision uses TP+FP detected-positive rows; recall uses TP+FN expected-positive rows; specificity uses TN+FP expected-negative rows; accuracy uses all labeled detection rows; median duration uses observations with recorded duration; candidate-only true-positive detections bind matched baseline and candidate observations. Mixed declared grades are not represented as exclusively independent, and labels are not external attestations.

**R2-F3 — supported PDF font repertoire.** Validate every dynamic narrative, metadata, rubric revision (including page footer), table and score text against the normal font and dynamic headings/table headers against the bold-face glyph map. Unsupported characters cause an error before immutable publication. Supported glyphs stay selectable. The font policy does not promise universal emoji, multilingual fallback or accessibility qualification.

### R3 self-review correction record — reporting generator 0.2.2

**R3-F1 — empirical versus nonempirical evidence eligibility.** Grades linked to measured
observations are divided into synthetic demonstration, nonempirical declarations
(documentation-only and anecdotal), and empirical *source declarations* (small pilot,
controlled local and independently reproduced). Reporting distinguishes synthetic-only,
mixed synthetic, nonempirical-only, mixed empirical/nonempirical, and empirical-only
declarations. Recorded pass gates plus numerically scored criteria cannot yield
recorded requirements met if any measured support is synthetic or nonempirical.
This deliberately conservative run-wide policy avoids presenting a computed metric
with documentation-only/anecdotal contributors as an empirical qualification.
None of these grades has been independently attested, and even recorded readiness
does not authorize adoption or assert independently validated source authenticity.

**R3-F3 — actual glyph and footer semantics.** A Unicode code point is accepted for
PDF rendering only when the selected TrueType font maps it to a nonzero
glyph index. ReportLab's bundled Vera maps some mathematical characters to
the missing .notdef glyph at index zero, even when text extraction recovers
the original Unicode text. The generator now rejects those cases before
publication and refuses Cc control characters in the raw canvas footer
rubric_revision field (paragraph whitespace normalization does not apply to
canvas text). The existing font selection, immutable publication and
page/long-table contracts are unchanged. This validates glyph mapping, not
comprehensive typography, shaping, script support or accessibility.

The regression corpus is tests/test_reporting_r3.py, including known-bad
controlled mutations and empirical/supported-Unicode positive controls.
E-900/E-901 historical input, PDF, manifest and analysis files remain byte-frozen.
No Google Drive source has been modified by these implementation corrections.


### Opt-in replay population integrity — reporting generator 0.2.3

E-017 v3 uses an optional, versioned `Evidence.replay_manifest` with a nonempty
map of evidence-root-relative paths to SHA-256 values. The evidence anchor must
appear in that map with the same digest. Existing evidence without this field
retains its original verification behavior. For an opted-in receipt the verifier
checks every member and only reports VERIFIED LOCAL REPLAY POPULATION when all
members and the anchor match. Both validate-run and build-report require that
verification to succeed, including when a caller omits an evidence root.
Absent, changed or unsafe members block regeneration. The checked-in structural
schema reflects the optional extension; historic report inputs remain readable.

This is complete byte-integrity verification of the producer-declared member
population, not an independent runtime attestation or semantic replay engine.
E-017 constructs the manifest only after independently replaying its required
population. To re-adjudicate outcomes, run the experiment-specific consumer.
Old report inputs without a replay manifest remain historical snapshots, not
proof that all original raw evidence is currently available.


### E-017 v3 population completeness — reporting generator 0.2.4

The existing opt-in manifest contract remains unchanged for ordinary reports.
E-017 Q1-local-r2-v3 requires its replay-population receipt and an exact frozen
stage-relative path-set identity, independently derived from the versioned
fixtures and required capture lifecycle. For this protocol a dropped field,
dropped aggregate, truncated member map, equal-count path substitution or
detached gate reference fails verification, rather than falling back to
individual normalized receipts. The independent fixture-derived path oracle
is exercised by the E-017 offline tests. Relocating stage directories does
not change the normalized path identity. All underlying bytes still require
hash verification; a path-set identity alone does not establish integrity.
This is a protocol-specific completeness check, not a semantic replay or
runtime attestation system. Earlier protocols retain their historical
verification semantics; their reports do not establish current availability
of complete replay evidence.
