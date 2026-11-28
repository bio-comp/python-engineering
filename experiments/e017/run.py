"""Explicit local, credential-free E-017 extraction and lookup execution."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from experiments.e017.oracle import (
    Fixture,
    Receipt,
    Stage,
    State,
    Verdict,
    digest,
    extraction_control_correct,
    judge_logs,
    load_fixtures,
    policy_control_correct,
)

HERE = Path(__file__).resolve().parent
INTEGRITY = (
    "sha512-+aWuZdFhLhVq8aPR0K6qEQfwZlZzsiKjRynqvkFL9oYy4H9q7q67wNq"
    "REORs8ebYGMXPT8JGYhczNMxNp2evnw=="
)


def materialize(case: Fixture, root: Path) -> None:
    root.mkdir()
    for name, content in case.files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode())


def snapshot(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("unexpected symlink in fixture")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    return result


def environment(root: Path, node: Path, uv: Path) -> dict[str, str]:
    home = root / "home"
    home.mkdir()
    return {
        "HOME": str(home),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "PATH": os.pathsep.join(
            (str(node.parent), str(uv.parent), str(Path(sys.executable).parent), os.defpath)
        ),
        "LOG_FORMAT": "json",
        "LOG_LEVEL": "debug",
        "RENOVATE_CACHE_DIR": str(root / "cache"),
        "RENOVATE_BASE_DIR": str(root / "base"),
        "RENOVATE_AUTODISCOVER": "false",
        "RENOVATE_ALLOW_SCRIPTS": "false",
        "RENOVATE_ALLOW_PLUGINS": "false",
        "RENOVATE_EXPOSE_ALL_ENV": "false",
        "RENOVATE_BINARY_SOURCE": "global",
        "UV_PYTHON_DOWNLOADS": "never",
    }


def version(command: list[str], env: dict[str, str], cwd: Path) -> str:
    return subprocess.run(
        command, env=env, cwd=cwd, check=True, capture_output=True, text=True, timeout=30
    ).stdout.strip()


def distribution(prefix: Path) -> str:
    lock = (prefix / "package-lock.json").read_bytes()
    data = json.loads(lock)
    entry = data["packages"]["node_modules/renovate"]
    if entry["version"] != "45.3.2" or entry["integrity"] != INTEGRITY:
        raise ValueError("unexpected npm resolution")
    package = prefix / "node_modules/renovate"
    if json.loads((package / "package.json").read_bytes())["version"] != "45.3.2":
        raise ValueError("unexpected installed package version")
    # Fingerprint the installed Renovate package bytes and npm dependency lock.
    # This is not attestation of native dependencies or original tarball bytes.
    parts = [digest(lock)]
    for path in sorted(package.rglob("*")):
        if path.is_file() and not path.is_symlink():
            parts.append(path.relative_to(package).as_posix() + ":" + digest(path.read_bytes()))
    return digest("\n".join(parts).encode())


def source_identity() -> dict[str, object]:
    repo = HERE.parents[1]
    git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            env=git_env,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()

    if Path(git("rev-parse", "--show-toplevel")).resolve() != repo:
        raise ValueError("source worktree identity mismatch")
    files = git("ls-files", "experiments/e017").splitlines()
    return {
        "source_commit": git("rev-parse", "--verify", "HEAD"),
        "source_dirty": bool(git("status", "--porcelain", "--untracked-files=all")),
        "source_files": {name: digest((repo / name).read_bytes()) for name in files},
        "pyproject_sha256": digest((repo / "pyproject.toml").read_bytes()),
        "lockfile_sha256": digest((repo / "uv.lock").read_bytes()),
    }


def run_case(
    case: Fixture,
    stage: Stage,
    run_root: Path,
    prefix: Path,
    node: Path,
    uv: Path,
    distribution_hash: str,
    repetition: int,
) -> Verdict:
    case_root = run_root / f"{case.case_id}-{stage}-{repetition}"
    case_root.mkdir()
    fixture = case_root / "fixture"
    materialize(case, fixture)
    env = environment(case_root, node, uv)
    executable = prefix / "node_modules/renovate/dist/renovate.js"
    tool = version([str(node), str(executable), "--version"], env, fixture)
    if tool != "45.3.2" or platform.python_version() != "3.14.10":
        raise ValueError("tool or Python version mismatch")
    node_version = version([str(node), "--version"], env, fixture)
    uv_version = version([str(uv), "--version"], env, fixture)
    if node_version != "v26.13.1" or not uv_version.startswith("uv 0.13.9 "):
        raise ValueError("runtime version mismatch")
    command = [str(node), str(executable), "--platform=local", f"--dry-run={stage}"]
    before = snapshot(fixture)
    start = time.monotonic()
    proc = subprocess.run(
        command, cwd=fixture, env=env, capture_output=True, check=False, timeout=180
    )
    receipt = Receipt(
        case_id=case.case_id,
        stage=stage,
        fixture_sha256=case.fingerprint(),
        distribution="npm-45.3.2-re2-fallback",
        tool_version="45.3.2",
        distribution_sha256=distribution_hash,
        node_version=node_version,
        python_version=platform.python_version(),
        uv_version=uv_version,
        command=tuple(command),
        environment=env,
        executed_at=datetime.now(UTC).isoformat(),
        returncode=proc.returncode,
        elapsed_seconds=time.monotonic() - start,
        stdout_sha256=digest(proc.stdout),
        stderr_sha256=digest(proc.stderr),
        before=before,
        after=snapshot(fixture),
    )
    (case_root / "stdout.jsonl").write_bytes(proc.stdout)
    (case_root / "stderr.txt").write_bytes(proc.stderr)
    (case_root / "receipt.json").write_text(receipt.model_dump_json(indent=2))
    verdict = judge_logs(case, stage, receipt, proc.stdout, proc.stderr)
    (case_root / "verdict.json").write_text(verdict.model_dump_json(indent=2))
    print(
        json.dumps(
            {
                "event": "case_adjudicated",
                "case": case.case_id,
                "stage": stage,
                "repetition": repetition,
                "state": verdict.state,
                "diagnostics": verdict.diagnostics,
            }
        ),
        flush=True,
    )
    return verdict


def validate_policies(root: Path, prefix: Path, node: Path, uv: Path) -> bool:
    policies = json.loads((HERE / "policies.json").read_bytes())
    all_correct = True
    for name, config in policies.items():
        case_root = root / f"policy-{name}"
        case_root.mkdir()
        path = case_root / "candidate.json"
        path.write_text(json.dumps(config, indent=2))
        before = digest(path.read_bytes())
        env = environment(case_root, node, uv)
        command = [
            str(node),
            str(prefix / "node_modules/renovate/dist/config-validator.js"),
            "--strict",
        ]
        if name != "administrative":
            command.append("--no-global")
        command.append(str(path))
        start = time.monotonic()
        proc = subprocess.run(
            command, cwd=case_root, env=env, check=False, capture_output=True, timeout=60
        )
        (case_root / "stdout.jsonl").write_bytes(proc.stdout)
        (case_root / "stderr.txt").write_bytes(proc.stderr)
        expected_valid = name in {"repository", "administrative"}
        correct = before == digest(path.read_bytes()) and policy_control_correct(
            name, path.read_bytes(), proc.stdout, proc.stderr, proc.returncode
        )
        (case_root / "receipt.json").write_text(
            json.dumps(
                {
                    "command": command,
                    "environment": env,
                    "expected_valid": expected_valid,
                    "returncode": proc.returncode,
                    "stdout_sha256": digest(proc.stdout),
                    "stderr_sha256": digest(proc.stderr),
                    "config_sha256": before,
                    "elapsed_seconds": time.monotonic() - start,
                    "control_correct": correct,
                    "scope": "schema validation only",
                },
                indent=2,
            )
        )
        print(
            json.dumps(
                {
                    "event": "config_adjudicated",
                    "case": name,
                    "correct": correct,
                    "exit": proc.returncode,
                }
            ),
            flush=True,
        )
        all_correct = all_correct and correct
    return all_correct


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npm-prefix", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stage", choices=("extract", "lookup"), default="extract")
    parser.add_argument("--policies", action="store_true")
    args = parser.parse_args()
    stage: Stage = args.stage
    prefix = args.npm_prefix.resolve(strict=True)
    root = args.out.resolve()
    root.mkdir(mode=0o700)
    node = Path(shutil.which("node") or "").resolve(strict=True)
    uv = Path(shutil.which("uv") or "").resolve(strict=True)
    dist = distribution(prefix)
    fixtures = load_fixtures(HERE / "corpus.json")
    (root / "run-identity.json").write_text(
        json.dumps(
            {
                **source_identity(),
                "corpus_sha256": digest((HERE / "corpus.json").read_bytes()),
                "policy_sha256": digest((HERE / "policies.json").read_bytes()),
                "distribution_sha256": dist,
                "npm_lock_sha256": digest((prefix / "package-lock.json").read_bytes()),
                "npm_resolution_integrity": INTEGRITY,
                "node_sha256": digest(node.read_bytes()),
                "uv_sha256": digest(uv.read_bytes()),
                "platform": platform.platform(),
                "condition": "existing npm installation; native RE2 unavailable; not OCI",
                "oci": "BLOCKED",
                "dependabot": "BLOCKED",
                "authenticated_pr": "NOT_APPLICABLE",
                "lookup_index": "dated live observation; release availability not frozen",
                "lookup_correctness": "BLOCKED: no frozen release availability oracle",
            },
            indent=2,
        )
    )
    correct = True
    for case in fixtures:
        if stage == "lookup" and case.case_id != "mixed-extraction":
            continue
        outcomes = [
            run_case(case, stage, root, prefix, node, uv, dist, i)
            for i in range(1, 3 if stage == "extract" else 2)
        ]
        correct = correct and all(
            extraction_control_correct(outcome)
            if stage == "extract"
            else outcome.state == State.PASS
            for outcome in outcomes
        )
        if stage == "extract":
            first = root / f"{case.case_id}-extract-1/verdict.json"
            second = root / f"{case.case_id}-extract-2/verdict.json"
            repeat_equal = first.read_bytes() == second.read_bytes()
            print(
                json.dumps(
                    {"event": "repeat_comparison", "case": case.case_id, "equal": repeat_equal}
                ),
                flush=True,
            )
            correct = correct and repeat_equal
    if args.policies:
        correct = validate_policies(root, prefix, node, uv) and correct
    # Even a fully passing extraction run is not Q1 qualification.
    return 0 if correct else 1


if __name__ == "__main__":
    raise SystemExit(main())
