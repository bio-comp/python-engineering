# E-015 — Offline citation-abstention controls

Citeprobe is an **unqualified, pre-alpha third-party candidate**. These tests
use an exact Git commit pinned in an isolated `citeprobe-lab` uv dependency
group; they do not install it as a default project dependency or connect it
to any scheduled task.

Run:

    uv run --locked --group citeprobe-lab pytest -q experiments/citeprobe/test_offline_abstention.py

The tests assert Citeprobe exit code 3 for inconclusive evidence, including
with --fail-on never; a scheduled pipeline must interpret the structured
result and not silently convert 3 into a passing verification.

The tests deliberately provide empty caches and `--offline` so even a valid
DOI must remain inconclusive. A fake DOI, a valid DOI, and an author/title
example cannot establish bibliographic identity without independent source
metadata. The tests examine provider status and policy behavior; they are
**not positive verification tests** and do not assess source-to-claim support.

A fully useful next stage requires independently curated primary bibliographic
records, falsified author/title/year/DOI examples, retractions, provider
timeouts and 429s, conflicting sources, and a separate claim-to-source
grounding oracle. Do not modify Prompt Research, llm_evaluation,
Bioinformatics Discovery, or scheduled automations as part of this pilot.
