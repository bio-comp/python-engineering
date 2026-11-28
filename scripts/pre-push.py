#!/usr/bin/env python3
"""Fail-closed outgoing-ref gate for a clean single-branch HEAD push."""

import subprocess
import sys


def output(*command: str) -> str:
    return subprocess.check_output(command, text=True).strip()


def main() -> int:
    refs = [line.split() for line in sys.stdin.read().splitlines()]
    head = output("git", "rev-parse", "HEAD")
    branch = output("git", "symbolic-ref", "HEAD")
    if (
        len(refs) != 1
        or len(refs[0]) != 4
        or refs[0][0] != branch
        or refs[0][1] != head
        or not refs[0][2].startswith("refs/heads/")
    ):
        print("Ref verification failed: qualify a single current HEAD branch only", file=sys.stderr)
        return 1
    if output("git", "status", "--porcelain=v1", "--untracked-files=normal"):
        print("Ref verification failed: dirty worktree", file=sys.stderr)
        return 1
    checks = [
        ["uv", "lock", "--check"],
        ["uv", "sync", "--locked"],
        ["uv", "run", "--locked", "ruff", "check", "--no-fix", "."],
        ["uv", "run", "--locked", "ruff", "format", "--check", "."],
        ["uv", "run", "--locked", "mypy", "src", "tests"],
        ["uv", "run", "--locked", "mypy", "--strict", "experiments/e017"],
        [
            "uv",
            "run",
            "--locked",
            "pytest",
            "--randomly-seed=101",
            "--cov=python_engineering",
            "--cov-branch",
            "--cov-report=term-missing",
            "-q",
        ],
        ["uv", "build"],
    ]
    for cmd in checks:
        print("CHECK: " + " ".join(cmd), flush=True)
        if subprocess.run(cmd, check=False).returncode:
            print("BLOCKED: failed verification command", file=sys.stderr)
            return 1
    print(f"Qualified intended outgoing SHA: {head}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
