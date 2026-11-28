# E-017 — local dependency-maintenance qualification harness

Issue #21. This is experimental implementation, not an active Renovate configuration,
production policy, adoption decision, or substitute for the canonical experiment record.

## Reproduction

Use Python 3.14.10, uv 0.13.9 and an isolated npm installation of Renovate 45.3.2
(Node 26.13.1). The npm arm is distinct from the official OCI distribution.
Provide the npm prefix containing node_modules and package-lock.json; the runner
records distribution and source identities. No installation, credentials or live
tool execution occur during ordinary pytest collection or testing.

From the repository root, after uv sync --locked:

```sh
uv run --locked pytest --randomly-seed=101 -q experiments/e017
uv run --locked mypy --strict experiments/e017
# Create a new private output directory outside the repository.
uv run --locked python -m experiments.e017.run --npm-prefix "$PREFIX" --out "$OUT/extract" --policies
uv run --locked python -m experiments.e017.run --npm-prefix "$PREFIX" --out "$OUT/lookup" --stage lookup
uv run --locked python -m experiments.e017.updates --npm-prefix "$PREFIX" --out "$OUT/updates"
uv run --locked python -m experiments.e017.report --root "$OUT" --extract "$OUT/extract" --lookup "$OUT/lookup" --updates "$OUT/updates" --out "$OUT/report"
```

Live failures are evidence, not a reason to discard output. Lookup can exit
nonzero when Renovate exits zero. The report requires clean, matching source
identities and replays extraction, lookup, configuration and update verdicts
from typed receipts and retained raw artifacts. It uses the existing reporting
system. R2 evidence schema v3 binds all receipts to the exact source, fixture,
distribution, interpreter, executable and stage identities. The update arm
retains initial, immediate generated, final and repeated byte snapshots, plus
the actual resolver invocations (including attempted and resulting trees).
Missing or contradictory evidence prevents report admission; the consumer never
promotes a stored verdict without replay. Synthetic offline tests exercise the
same consumer through an explicit synthetic-only interface; the report CLI does
not admit synthetic evidence as genuine execution. The original v1 and R1 v2 evidence
remain immutable; new launch timestamps and invocation context bindings cannot
be reconstructed retrospectively. The original v1 also lacks independent
intermediate snapshots and child resolver receipts.

### Execution chronology and report retention (v3)

A stage identity's executed_at is the time the identity is finalized, before
case execution. Each receipt records started_at just before launching the
subprocess and executed_at immediately after it returns, before post-process
snapshot/receipt persistence. elapsed_seconds is independently monotonic;
it is not used to infer an exact wall-clock start. For the sequential Q1
workflow, stage/case/phase intervals must be ordered and child resolver
intervals contained within outer process intervals. Same-host wall times allow
one millisecond of log quantization; substantial clock reversals or missing
intervals are not qualified. This is not external clock attestation.

Each extraction/lookup invocation supplies a context derived from its stage
identity and case/repetition. The three material Renovate events must carry
that context, a single process/host/repository identity and compatible times
inside the recorded interval. Startup records need not carry repository data.

The generated report input embeds a versioned replay-member manifest covering
the exact retained expected inputs, run identities, raw logs/receipts, resolver
invocations, all required snapshots and verdicts. The shared reporting
verifier checks every member's local bytes. For v3 reports both
validate-run and build-report require an evidence root and refuse incomplete,
altered or unavailable replay populations. This does not rerun the tools or
attest runtime origin; use the E-017 report command above for semantic replay.
The v3 protocol additionally fixes the required stage-relative path population
at 754 members (135 extraction, 14 lookup, 605 update). The shared verifier
checks its frozen path-set identity independently of the submitted manifest,
so removing the manifest or replacing required paths with unrelated paths
cannot yield a complete replay verification. Changed fixture populations need
a separately versioned protocol. Missing or additional unexpected replay files
may block report admission; preserve their raw failure evidence.
Older report inputs and already-rendered reports are historical snapshots,
not evidence that their raw replay population is currently available.

## Scope

The JSON corpus contains independently specified expectations, including deliberate
exclusions and an invalid TOML negative control. A separate frozen-revision
pre-commit case extends the original corpus without changing its bytes. A separate frozen manifest/lock
population contains the targeted requests calibration regression and idna case.
The latter is new evaluation material, not blind data. Lookup is a dated live
observation; release availability is not frozen or independently established.
Native uv is the targeted lock comparator, not a proposal-generation bot.
The Renovate update arm calls pinned internal components, not authenticated PR
generation. The failed-conflict operation may mutate its staging manifest;
it must not be interpreted as atomic rollback or published output.
The official OCI and genuine Dependabot arms are blocked until separately executed.
No installation compatibility, production policy enforcement or Q2 qualification
is claimed. Keep evidence private until separately reviewed for publication.
