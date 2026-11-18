# E-005: Pydantic-aware Python type-checker comparison

This is a **synthetic fixture and diagnostic collection**, not a migration or
a claim that any one checker is superior. It complements Issue #5's Ruff/mypy
configuration study and leaves the existing mandatory mypy gate unchanged.

Optional, exact-locked comparator group: mypy 1.20.2 (with and without
`pydantic.mypy`), Pyright 1.1.414, basedpyright 1.40.2, ty 0.0.95, and
Pyrefly 1.4.1. Python 3.14.10, Pydantic 2.14.1 and pydantic-settings 2.16.3.
These are deliberately **not** interchangeable strictness profiles:
mypy strict, mypy strict + native Pydantic plugin, Pyright/basedpyright strict,
Pyrefly strict preset, and ty's recorded default diagnostics.

Run independently, without editing the repository's production config:

    uv run --locked --group e005-typing pytest -q experiments/e005/test_matrix.py

Each case contains its own standalone Pydantic model/call site. The harness
writes only temporary Python files, validates expected runtime acceptance with
the pinned Pydantic release, and records diagnostics from each checker. Runtime results use a structured
subprocess protocol that catches only actual `pydantic.ValidationError`
instances; unrelated exceptions fail the experiment. Checker file identities
must match the generated fixture path exactly, and summary/exit mismatches
are fatal rather than silently reducing error counts. The
Pydantic runtime oracle is the authority for **constructor acceptance only**:
it does not imply a checker must accept all lax constructor calls, nor that
type checking can detect dynamic runtime/schema properties.

A deliberate falsifier is default `extra='ignore'`: Pydantic accepts unknown
constructor input but discards it. This differs materially from
`extra='allow'`, which stores unknown fields. Pyrefly's documentation contains
phrasing conflating those configurations, so test the runtime contract.

**Not yet covered:** full discriminator/JSON Schema semantics, validators,
nested containers, arbitrary aliases, Pydantic generics, external stubs,
cross-version regressions, cold/warm repetitions and coding-agent error
recovery. E-005 owns those additions; do not change protected repositories or
auto-install a new type checker in their CI.

## Raw measurement and replay contract

    uv run --locked --group e005-typing python -m experiments.e005.matrix

The JSON output includes the Git HEAD and dirty flag, hashes of the complete
fixture oracle (including expected outcomes and rationale) and harness sources,
the structured runtime protocol and controlled subprocess-environment digest,
actual venv/site-packages paths, package versions, per-checker configuration
contents and SHA-256 digests, complete exact command lines and cwd, exit codes,
original stdout/stderr and hashes, and normalized per-case diagnostic source
locations. `ty` uses its recorded default configuration (no config file);
mypy strict with and without Pydantic plugin are separate arms. The temporary
`fixture_paths` mapping connects ephemeral paths to stable case IDs.
No experimental stdout/stderr or host paths are checked into Git; review raw
receipts before sharing to ensure no accidental disclosures.

The runtime environment is isolated from inherited settings variables and
Python optimization flags. The Pyright family uses the **active virtual
environment** (not the resolved system-interpreter symlink) and fails if its
configuration cannot identify a real installed venv. A separate verbose
resolution probe for both Pyright-derived checkers must list the exact active
site-packages directory; raw probe outputs and hashes are retained with their
corresponding tool measurements. These are scientific
measurement integrity gates, not new production typing defaults. Historical
16-case diagnostic counts are retained as preliminary and unqualified;
do not claim broad speed, completeness, precision, or static typing agreement.
