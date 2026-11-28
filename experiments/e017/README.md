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
identities and replays the extraction/lookup oracle from raw receipts. It uses
the existing reporting system. Update verdicts in the report
are runner-recorded; independent review must inspect their raw artifacts.
Configuration controls are independently replayed from raw logs.

## Scope

The JSON corpus contains independently specified expectations, including deliberate
exclusions and an invalid TOML negative control. A separate frozen manifest/lock
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
