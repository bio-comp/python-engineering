# Ruff / mypy config-signal controls

These are **synthetic diagnostic fixtures**, not production source or global
quality policy. The deliberate defects are stored as `.py.txt` so they do not
enter repository-wide lint/type checks. The experiment compares two separately
loaded, real `pyproject.toml`-format fragments under Python **3.14.10**,
Ruff **0.17.5**, and mypy **1.20.2**.

Run `uv run --locked pytest --randomly-seed=101 -q tests/test_quality_config_matrix.py`
for the bounded diagnostic and configuration controls. The experiment tests
configuration selection separately from seeded diagnostic behavior. A selected
family/option is **not** evidence that it detects a fixture defect.

## Configured selections versus exercised diagnostics

- **Mandatory Ruff baseline in both arms:** `E`, `F`, `I`, `B`, `UP`,
  `RUF`. Its seeded bad fixture reports `I001` and `B006`; the remaining
  baseline families have no independently demonstrated diagnostic increment.
- **Additional Ruff candidate families:** `S`, `T20`, `DTZ`, `C4`,
  `SIM`, `PIE`, `ASYNC`, `PT`, `TRY`, `LOG`.
  Only `T201`, `S602`, `S607`, `DTZ005`, and `C416` are exercised
  as candidate-only seeded diagnostics. `SIM`, `PIE`, `ASYNC`, `PT`,
  `TRY`, and `LOG` have **no diagnostic fixture coverage** here; other
  rules within the exercised families likewise remain unverified.
- **Mandatory mypy baseline:** `strict = true` and
  `python_version = "3.14"`. The candidate adds `warn_unreachable = true`,
  `disallow_any_explicit = true`, and `enable_error_code` selections for
  `possibly-undefined`, `explicit-override`, `exhaustive-match`,
  `redundant-expr`, `ignore-without-code`, and `unused-awaitable`.
  Seeded candidate-only findings are `possibly-undefined`,
  `explicit-override`, `exhaustive-match`, and `explicit-any` (from
  `disallow_any_explicit`). `warn_unreachable`, `redundant-expr`,
  `ignore-without-code`, and `unused-awaitable` have no separately verified
  diagnostic fixture here.

The known-good fixture must remain diagnostic-free under both tools and both
configurations. Tests also assert the **complete parsed configurations**,
checker versions, and byte-level SHA-256 identities of both configs and fixtures
so silent omission or fixture drift cannot be mistaken for an experiment result.

## Frozen inputs (SHA-256)

| Experiment input | SHA-256 |
| --- | --- |
| `fixtures/known_bad.py.txt` | `7b80ae919768d2f069ea7e9341c21294f53df84eb7e07a8d652e771813ef9d2d` |
| `fixtures/known_good.py.txt` | `7a0beb65b16416964c06bde5be97a587fc96383742bbcfd13ab85cf1d6a2700a` |
| `base.pyproject.toml` | `bc679fa9722f77df12864d267adad015872319ac97910542fdd85bdb7ae37148` |
| `candidate.pyproject.toml` | `18a0f97ded9bdf5d2bf29f61f3dcfb206a92e15e0a945a092c053981e0cefd16` |

Any justified byte change requires an explicit revised digest and scientific
rationale; updating the expected hash alone is not evidence of correctness.

## Scientific boundary and remaining Issue #5 acceptance

These synthetic observations do **not** establish representative precision,
false-positive rates, check placement, tool superiority, real-project coverage,
agent recovery, or E-001/E-005 qualification. Remaining work includes frozen
independently labeled bad/legitimate cases for the unexercised checks; JSON
machine-readable finding inventories; verified incremental unique/duplicate
signal and analyzer-overlap controls; false-positive adjudication; cold/warm
timing; agent-recovery results; and an adequately representative exact-version
typing/Pydantic comparison. No results for those outcomes are asserted here.

The root `pyproject.toml`, mandatory Ruff/mypy gates, installed hooks, and
application repositories remain unchanged. The candidate is experimental only,
not an adoption or CI-gating recommendation. Issue #5 remains open.
