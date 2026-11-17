# Python Engineering Laboratory

A public, independent executable laboratory for reproducible Python engineering experiments and synthetic correctness fixtures.

**Authority boundary:** This repository owns source code, synthetic fixtures, test oracles, package and CI configuration, and immutable implementation artifacts. The Python Engineering Google Drive canonicals remain the sole authority for research interpretation, current practices, tool adoption status, experiment definitions/status, source qualification, and decisions. No private canonical text or service credentials belong here.

Initial work: [bootstrap #1](https://github.com/bio-comp/python-engineering/issues/1) and [E-010 #2](https://github.com/bio-comp/python-engineering/issues/2). Four experimental retrieval arms are proposed; no coding-agent efficacy evidence has been collected.

No license has been granted or selected for this repository.

## Local verification

Requires uv; laboratory targets CPython 3.14.10. Run uv python install 3.14.10 and uv sync --locked, followed by the independent CI checks in .github/workflows/ci.yml. Hooks are opt-in; see scripts/install-hooks.sh.

Synthetic task fixtures are authored independently and labeled calibration or published-test material. Public fixtures cannot be described as blind to models that can retrieve this repository.

## E-010 offline demonstration (no model or MCP trial)

From the repository root, run:

    uv run --locked python -m python_engineering.e010.demo
    uv run --locked python -m python_engineering.e010.demo --manifest-dir /tmp/e010-unrun-manifests

The second command creates four exclusive-write, SHA-256-fingerprinted, clearly **not-run** records with the actual local Python version, package versions, OS, Git SHA and dirty-worktree flag. It does not execute coding agents or retrieved commands. A public repository cannot provide blind held-out fixtures; the published tests here are not blinded, and true held-out oracle material must be stored outside any solving-agent-readable checkout. The scorer checks frozen input hashes and directory separation but **does not provide operating-system isolation**, authenticate agent-tool permissions, or prove code correctness from self-reported outputs. Do not score real agent outputs without a trusted execution boundary and independent instrumentation.
