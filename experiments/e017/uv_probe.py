"""Standard-library-only child wrapper for the actual uv resolver invocations.

Executed with the pinned base interpreter, not the laboratory virtualenv.
No network activity occurs unless the explicit experiment calls this wrapper.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


def inventory(root: Path) -> dict[str, str]:
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("unexpected symlink in resolver snapshot")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def main() -> int:
    root, fixture, uv, binding, environment, *args = sys.argv[1:]
    case = Path(root)
    cwd = Path(fixture)
    if Path.cwd() != cwd:
        raise ValueError("unexpected uv working directory")
    context = json.loads(binding)
    env = json.loads(environment)
    attempts = case / "uv-attempts"
    attempts.mkdir(exist_ok=True)
    number = len(list(attempts.iterdir())) + 1
    if number > 4:
        raise ValueError("unexpected uv invocation count")
    target = attempts / str(number)
    target.mkdir()
    with (case / "uv-invocations.jsonl").open("a") as log:
        log.write(json.dumps(args) + "\n")
    shutil.copytree(cwd, target / "before", symlinks=True)
    started = time.monotonic()
    command = [uv, *args]
    proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, check=False, timeout=150)
    shutil.copytree(cwd, target / "after", symlinks=True)
    (target / "stdout").write_bytes(proc.stdout)
    (target / "stderr").write_bytes(proc.stderr)
    phases = ("initial-check", "update", "lock-check", "repeat")
    (target / "receipt.json").write_text(
        json.dumps(
            {
                **context,
                "operation": phases[number - 1],
                "command": command,
                "environment": env,
                "cwd": str(cwd),
                "executed_at": datetime.now(UTC).isoformat(),
                "returncode": proc.returncode,
                "before": inventory(target / "before"),
                "after": inventory(target / "after"),
                "elapsed_seconds": time.monotonic() - started,
                "stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(),
                "stderr_sha256": hashlib.sha256(proc.stderr).hexdigest(),
            },
            indent=2,
        )
    )
    sys.stdout.buffer.write(proc.stdout)
    sys.stderr.buffer.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
