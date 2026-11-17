# Python Engineering Laboratory

A public, independent executable laboratory for reproducible Python engineering experiments and synthetic correctness fixtures.

**Authority boundary:** This repository owns source code, synthetic fixtures, test oracles, package and CI configuration, and immutable implementation artifacts. The Python Engineering Google Drive canonicals remain the sole authority for research interpretation, current practices, tool adoption status, experiment definitions/status, source qualification, and decisions. No private canonical text or service credentials belong here.

Initial work: [bootstrap #1](https://github.com/bio-comp/python-engineering/issues/1) and [E-010 #2](https://github.com/bio-comp/python-engineering/issues/2). Four experimental retrieval arms are proposed; no coding-agent efficacy evidence has been collected.

No license has been granted or selected for this repository.

## Local verification

Requires uv; laboratory targets CPython 3.14.10. Run uv python install 3.14.10 and uv sync --locked, followed by the independent CI checks in .github/workflows/ci.yml. Hooks are opt-in; see scripts/install-hooks.sh.

Synthetic task fixtures are authored independently and labeled calibration or published-test material. Public fixtures cannot be described as blind to models that can retrieve this repository.


## Evidence report generation (experimental)

The versioned `reporting` module validates frozen run data and produces machine-readable analysis,
concise/detailed Markdown, and a paginated selectable PDF with reproducibility hashes.
See [REPORTING.md](REPORTING.md) for schema, rubric semantics, evidence gates, layout,
reproduction commands, qualification limits and proposed canonical reconciliation.

The checked-in E-900/E-901 fixtures are **synthetic reporting demonstrations only**, not
real measurements, not a registered experimental protocol, and not evidence of any tool
superiority or adoption.

```bash
uv sync --locked
uv run --locked python -m python_engineering.reporting validate-run examples/synthetic_900.json
uv run --locked python -m python_engineering.reporting build-report examples/synthetic_900.json /tmp/pyeng-demo-report-new
```

ReportLab is a tested implementation dependency for this report renderer. Other proposed
PDF approaches and optional marimo exploration are not yet empirically qualified.
