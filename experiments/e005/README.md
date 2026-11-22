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

### Git source-revision provenance (R3)

`_git_revision()` resolves the source root from this harness file, then
invokes Git with an explicit environment that removes **all inherited
`GIT_*` variables** for repository discovery, commit identification and
dirty/untracked-file detection. That excludes repository/worktree/index/object
redirection (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`,
`GIT_COMMON_DIR`), Git command/config overrides (`GIT_CONFIG_*`),
namespaces and tracing. Unrelated platform process variables are retained
for normal Git executable and repository operation. Git discovers the
checkout's genuine `.git` directory **or linked-worktree `.git` file**
from the requested source path; a discovered top-level path that differs
from that expected source root **fails closed**. All three Git reads use
the same filtered environment, and a complete commit object ID is required.

The report's `git_revision` and `git_dirty` therefore describe the
intended Python Engineering checkout, not an unrelated Git repo supplied
by inherited automation environment. Isolated adversarial tests cover
foreign-repository redirection, alternate Git index/config/object
variables, real linked worktrees, clean/modified/untracked files,
root mismatch, and complete matrix execution under inherited Git
overrides. These source receipts are local replay evidence, **not external
attestation or a guarantee against arbitrary host/Git-install tampering**.

### Static-checker environment contract (R2)

All six checker arms, including mypy with the Pydantic plugin, and the
Pyright/basedpyright `--verbose` import-resolution probes receive the *same*
explicit environment built by `_checker_environment()`. No checker inherits
arbitrary parent-process variables. On macOS/Linux the entire allowlist is:

- `PATH=<active-venv>/bin:<os.defpath>` — finds executables in the active,
  locked environment before the OS's built-in default system directories;
  inherited `PATH` is **not** forwarded.
- `VIRTUAL_ENV=<active-venv>` — pins the checker-visible virtual environment.
- `HOME=<temporary-run>/checker-home` and
  `XDG_CONFIG_HOME`/`XDG_CACHE_HOME` underneath that directory — avoid
  ambient user configuration and caches.
- `PYTHONNOUSERSITE=1` and `PYTHONDONTWRITEBYTECODE=1` — disable user site
  imports and bytecode side effects.

Windows additionally requires `SYSTEMROOT` for OS process operation, and
fails explicitly if unavailable. No credentials, arbitrary `PYTHONPATH`,
`MYPYPATH`, `NODE_OPTIONS`, `UV_*`, dotenv or other inherited
configuration values are forwarded. Checker executables are resolved from
the active venv's scripts directory rather than from an inherited `PATH`.
Unsupported environments are not silently substituted. The policy is
versioned `e005-checker-environment-v1`.

The JSON measurement schema is deliberately versioned `e005-matrix-v2`
(additive extension). `checker_environment` records the exact nonsecret
applied name/value mapping, policy identifier, and SHA-256 of its canonical
JSON representation. Each checker/probe receipt includes the same environment
digest to prove the harness *intended* to use that policy for every invocation;
negative-control tests instrument actual subprocess calls. The digest is a
local replay fingerprint, **not cryptographic external attestation**. Absolute
temporary paths vary across runs; preserve the environment receipt alongside
each run's command, cwd, config and output receipts. Never publish raw checker
outputs without reviewing them for unintended disclosure.

R2 falsifier: two incompatible `demo_stubs.pyi` implementations
(`make_value() -> int` versus `-> str`) change mypy diagnostics when
`MYPYPATH` is inherited, but cannot alter diagnostics under this explicit
policy. The 16 frozen Pydantic cases and their expected outcomes are unchanged.

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
