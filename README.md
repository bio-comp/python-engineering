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

Reporting R1 corrections (generator 0.2.0) add long-cell PDF continuation,
atomic no-overwrite publication, matched-case comparisons, required-measurement
completeness, explicit root-confined receipt checks, Unicode font-repertoire
checks, and observation-linked independent-grade attribution. Historical E-900/E-901
synthetic artifacts remain frozen at generator 0.1.0; publish new reports
under new paths. See REPORTING.md for the exact corrected contracts.

## E-010 offline demonstration (no model or MCP trial)

From the repository root, run:

    uv run --locked python -m python_engineering.e010.demo
    uv run --locked python -m python_engineering.e010.demo --manifest-dir /tmp/e010-unrun-manifests

The second command creates four exclusive-write, SHA-256-fingerprinted, clearly **not-run** records with the actual local Python version, package versions, OS, Git SHA and dirty-worktree flag. It does not execute coding agents or retrieved commands. A public repository cannot provide blind held-out fixtures; the published tests here are not blinded, and true held-out oracle material must be stored outside any solving-agent-readable checkout. The scorer checks frozen input hashes and directory separation but **does not provide operating-system isolation**, authenticate agent-tool permissions, or prove code correctness from self-reported outputs. Do not score real agent outputs without a trusted execution boundary and independent instrumentation.
