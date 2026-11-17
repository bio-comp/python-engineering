# Ruff / mypy config-signal controls

These files are **synthetic test fixtures**, never production source. The
`.py.txt` suffix prevents deliberate defects from contaminating repository
lint or type checks. Use `pytest tests/test_quality_config_matrix.py` to
compare two actual `pyproject.toml`-format configuration fragments. Only
the relative change in diagnostics on the frozen fixtures is assessed. Findings
still require independent labels before a rule can become a mandatory gate.

The existing repository `pyproject.toml` remains unchanged. Both configurations
still include the mandatory Ruff/mypy baseline; the candidate only adds rules.
No mypy or Ruff option is automatically applied to other projects.
