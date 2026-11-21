#!/usr/bin/env python3
"""Fast staged-file hook; refuse unstaged edits to a checked Python path."""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"],
        check=True,
        capture_output=True,
    ).stdout
    selected = [
        path.decode()
        for path in staged.split(b"\0")
        if path and Path(path.decode()).suffix in {".py", ".pyi"}
    ]
    if not selected:
        return 0
    for name in selected:
        if subprocess.run(["git", "diff", "--quiet", "--", name], check=False).returncode:
            print(f"Unstaged edits in checked path: {name}", file=sys.stderr)
            return 1
    for command in (
        ["uv", "run", "--locked", "ruff", "check", "--no-fix", *selected],
        ["uv", "run", "--locked", "ruff", "format", "--check", *selected],
    ):
        if subprocess.run(command, check=False).returncode:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
