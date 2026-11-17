# E-013: Wheelgap target-wheel compatibility control

This directory contains a **synthetic mutation test**, not an installation
benchmark. The working laboratory `uv.lock` is copied without modification.
Mutants delete the advertised `sortedcontainers==2.4.0` universal wheel
while optionally retaining the source distribution. All tests are offline.

The positive control must report compatible wheels for Python 3.14 on
Linux x86-64, Linux ARM64, and musl/Alpine ARM64. The source-only and missing
mutants must report the corresponding gap and a nonzero exit code.

Run without promoting wheelgap into the normal developer baseline:

    uv run --locked --group wheelgap-lab pytest -q experiments/wheelgap/test_lockfile_wheels.py

Do not generalize this result to actual target-machine installation,
dependency advisories, or security. E-013 is a research candidate; future
tests must compare the check with true offline wheelhouse installs.
