"""Bounded live component/native-uv comparison; no authenticated bot actions."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import Field, TypeAdapter, ValidationError

from experiments.e017.oracle import Log, State, digest, unique_json
from experiments.e017.run import HERE, distribution, environment, snapshot, source_identity, version
from python_engineering.reporting.models import Contract

FIXTURES = HERE / "update_fixtures"
Arm = Literal["renovate", "native-uv"]
ARMS: tuple[Arm, ...] = ("renovate", "native-uv")


class Spec(Contract):
    case_id: str = Field(pattern=r"^[a-z0-9-]+$")
    dependency: str
    old_version: str
    new_version: str
    classification: Literal["calibration-regression", "independent"]


class Package(Contract):
    name: str
    version: str


class ArtifactError(Contract):
    fileName: str
    stderr: str


class Artifact(Contract):
    file: str | None
    error: ArtifactError | None
    contentsPresent: bool


class ComponentResult(Contract):
    msg: Literal["E017 component result"]
    level: int
    manifest: str
    repeatedManifest: str | None
    artifacts: tuple[Artifact, ...]


def lock_versions(raw: bytes) -> dict[str, str]:
    # Project only the package/version identity; uv itself verifies the
    # complete lockfile and its relationship to the manifest.
    data = tomllib.loads(raw.decode())
    values = data.get("package", [])
    result: dict[str, str] = {}
    for value in values:
        package = Package.model_validate({"name": value["name"], "version": value["version"]})
        if package.name in result:
            raise ValueError("duplicate lock package (outside single-version fixture scope)")
        result[package.name] = package.version
    if not result:
        raise ValueError("empty lock")
    return result


def update_errors(
    spec: Spec,
    initial: dict[str, bytes],
    expected_manifest: bytes,
    actual: dict[str, bytes],
    *,
    artifact: ComponentResult | None,
    arm: Arm,
    returncode: int,
    lock_check_exit: int | None,
    repeated: dict[str, bytes] | None,
) -> tuple[str, ...]:
    errors = []
    if returncode:
        errors.append("nonzero update exit")
    if arm == "renovate":
        if artifact is None or len(artifact.artifacts) != 1:
            errors.append("missing/duplicate artifact result")
        elif artifact.artifacts[0] != Artifact(file="uv.lock", error=None, contentsPresent=True):
            errors.append("artifact error or wrong artifact")
        if artifact is None or artifact.manifest.encode() != expected_manifest:
            errors.append("component replacement differs from expected")
        if artifact is None or artifact.repeatedManifest != expected_manifest.decode():
            errors.append("component replacement not idempotent")
    if set(actual) != set(initial):
        errors.append("file population changed")
    if actual.get("pyproject.toml") != expected_manifest:
        errors.append("wrong/missing manifest update")
    for name, data in initial.items():
        if name not in {"pyproject.toml", "uv.lock"} and actual.get(name) != data:
            errors.append("unrelated file changed")
    try:
        before = lock_versions(initial["uv.lock"])
        after = lock_versions(actual["uv.lock"])
        if before.get(spec.dependency) != spec.old_version:
            errors.append("incorrect starting lock version")
        before[spec.dependency] = spec.new_version
        if after != before:
            errors.append("incorrect lock version/population")
    except KeyError, ValueError, ValidationError, TypeError:
        errors.append("missing/malformed lock")
    if lock_check_exit != 0:
        errors.append("missing or failed independent uv lock check")
    if repeated is None or repeated != actual:
        errors.append("missing or changed repeated lock state")
    return tuple(errors)


def read_tree(root: Path) -> dict[str, bytes]:
    return {name: (root / name).read_bytes() for name in snapshot(root)}


def component_result(stdout: bytes) -> ComponentResult:
    if not stdout.endswith(b"\n"):
        raise ValueError("truncated component log")
    result = []
    unexpected_errors = []
    for line in stdout.splitlines():
        unique_json(line)
        log = Log.model_validate_json(line)
        if log.msg == "E017 component result":
            result.append(ComponentResult.model_validate_json(line))
        elif log.level >= 40 and log.msg != "RE2 not usable, falling back to RegExp":
            unexpected_errors.append(log.msg)
    if len(result) != 1:
        raise ValueError("missing/duplicate component result")
    if unexpected_errors and not any(item.error for item in result[0].artifacts):
        raise ValueError("unexpected component error without artifact error")
    return result[0]


def invocation_evidence(path: Path, dependency: str, conflict: bool) -> bool:
    if not path.is_file():
        return False
    try:
        records = []
        for line in path.read_bytes().splitlines():
            unique_json(line)
            records.append(TypeAdapter(list[str]).validate_json(line, strict=True))
    except ValueError, ValidationError:
        return False
    required = [["lock", "--check"], ["lock", "--upgrade-package", dependency]]
    if not conflict:
        required += [["lock", "--check"], ["lock"]]
    return records == required


def invoke(
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    root: Path,
) -> subprocess.CompletedProcess[bytes]:
    start = time.monotonic()
    proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, check=False, timeout=180)
    (root / f"{name}.stdout").write_bytes(proc.stdout)
    (root / f"{name}.stderr").write_bytes(proc.stderr)
    (root / f"{name}.json").write_text(
        json.dumps(
            {
                "command": command,
                "environment": env,
                "cwd": str(cwd),
                "returncode": proc.returncode,
                "elapsed_seconds": time.monotonic() - start,
                "stdout_sha256": digest(proc.stdout),
                "stderr_sha256": digest(proc.stderr),
            },
            indent=2,
        )
    )
    return proc


def run_arm(
    spec: Spec,
    arm: Arm,
    root: Path,
    prefix: Path,
    node: Path,
    uv: Path,
    cache: Path,
    repetition: int,
    conflict: bool = False,
) -> tuple[State, dict[str, bytes]]:
    case = root / f"{spec.case_id}-{arm}-{repetition}"
    case.mkdir()
    fixture = case / "fixture"
    fixture.mkdir()
    source = FIXTURES / spec.case_id
    for name in ("pyproject.toml", "uv.lock", "sentinel.txt"):
        shutil.copyfile(source / name, fixture / name)
    initial = read_tree(fixture)
    expected = (source / "expected.toml.txt").read_bytes()
    if conflict:
        expected = expected.replace(
            f'"{spec.dependency}=={spec.new_version}"'.encode(),
            (
                f'"{spec.dependency}=={spec.new_version}", "{spec.dependency}=={spec.old_version}"'
            ).encode(),
        )
    env = environment(case, node, uv)
    # Instrument actual uv invocations. Enforce the same exact Python and
    # public index, without forwarding ambient host config or credentials.
    shim = case / "bin"
    shim.mkdir()
    python = Path(sys.executable).resolve()
    (shim / "python").symlink_to(python)
    (shim / "python3").symlink_to(python)
    wrapper = shim / "uv"
    wrapper.write_text(
        f"#!{python}\n"
        "import json,os,sys\n"
        f"with open({str(case / 'uv-invocations.jsonl')!r}, 'a') as log:\n"
        "    log.write(json.dumps(sys.argv[1:])+'\\n')\n"
        f"os.environ['UV_PYTHON']={str(python)!r}\n"
        "os.environ['UV_PYTHON_DOWNLOADS']='never'\n"
        "os.environ['UV_DEFAULT_INDEX']='https://pypi.org/simple'\n"
        f"os.environ['UV_CACHE_DIR']={str(cache)!r}\n"
        f"os.execv({str(uv)!r},[{str(uv)!r},*sys.argv[1:]])\n"
    )
    wrapper.chmod(0o700)
    env["PATH"] = str(shim) + os.pathsep + env["PATH"]
    uv_command = str(wrapper)
    (case / "initial.json").write_text(json.dumps(snapshot(fixture), indent=2))
    check_before = invoke("initial-check", [uv_command, "lock", "--check"], fixture, env, case)
    if check_before.returncode:
        raise ValueError("initial frozen lock rejected")
    artifact = None
    if arm == "renovate":
        command = [
            str(node),
            str(HERE / "update_component.mjs"),
            str(prefix / "node_modules/renovate/dist"),
            str(fixture),
            str(case / "cache"),
            spec.dependency,
            spec.old_version,
            spec.new_version,
            "conflict" if conflict else "update",
        ]
        proc = invoke("update", command, fixture, env, case)
        if proc.returncode == 0:
            artifact = component_result(proc.stdout)
    else:
        (fixture / "pyproject.toml").write_bytes(expected)
        proc = invoke(
            "update", [uv_command, "lock", "--upgrade-package", spec.dependency], fixture, env, case
        )
    actual = read_tree(fixture)
    if conflict:
        # Conflicting requirements must produce a structured artifact error
        # or real resolver failure, and must not modify the starting lock.
        correct = (
            actual.get("uv.lock") == initial["uv.lock"]
            and actual.get("sentinel.txt") == initial["sentinel.txt"]
        )
        if arm == "renovate":
            correct = (
                correct
                and proc.returncode == 0
                and artifact is not None
                and (
                    len(artifact.artifacts) == 1
                    and artifact.artifacts[0].error is not None
                    and artifact.artifacts[0].error.fileName == "uv.lock"
                    and "No solution found" in artifact.artifacts[0].error.stderr
                    and actual.get("pyproject.toml") in {initial["pyproject.toml"], expected}
                    and set(actual) == set(initial)
                    and artifact.manifest.encode() == expected
                )
            )
        else:
            correct = correct and proc.returncode != 0 and b"No solution found" in proc.stderr
        correct = correct and invocation_evidence(
            case / "uv-invocations.jsonl", spec.dependency, True
        )
        manifest_mutated = actual.get("pyproject.toml") != initial["pyproject.toml"]
        errors: tuple[str, ...] = (
            ("conflict correctly rejected",) if correct else ("conflict control failed",)
        )
        if manifest_mutated:
            errors += ("failed operation left staged manifest modified; not atomic",)
        state = State.FAIL if correct else State.BLOCKED
        (case / "verdict.json").write_text(
            json.dumps(
                {
                    "state": state,
                    "expected_state": "FAIL",
                    "control_correct": correct,
                    "raw_manifest_mutated": manifest_mutated,
                    "diagnostics": errors,
                    "after": snapshot(fixture),
                },
                indent=2,
            )
        )
        return state, actual
    checked = invoke("lock-check", [uv_command, "lock", "--check"], fixture, env, case)
    repeat = invoke("repeat", [uv_command, "lock"], fixture, env, case)
    repeated = read_tree(fixture) if repeat.returncode == 0 else None
    errors = update_errors(
        spec,
        initial,
        expected,
        actual,
        artifact=artifact,
        arm=arm,
        returncode=proc.returncode,
        lock_check_exit=checked.returncode,
        repeated=repeated,
    )
    if not invocation_evidence(case / "uv-invocations.jsonl", spec.dependency, False):
        errors += ("missing or unexpected uv invocation evidence",)
    state = State.FAIL if errors else State.PASS
    (case / "verdict.json").write_text(
        json.dumps(
            {
                "state": state,
                "diagnostics": errors,
                "after": {n: digest(v) for n, v in actual.items()},
                "repeated": snapshot(fixture),
            },
            indent=2,
        )
    )
    return state, actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npm-prefix", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.out.resolve()
    root.mkdir(mode=0o700)
    prefix = args.npm_prefix.resolve(strict=True)
    node = Path(shutil.which("node") or "").resolve(strict=True)
    uv = Path(shutil.which("uv") or "").resolve(strict=True)
    env = environment(root, node, uv)
    if (
        platform.python_version() != "3.14.10"
        or version([str(node), "--version"], env, root) != "v26.13.1"
    ):
        raise ValueError("incorrect Python/Node condition")
    if not version([str(uv), "--version"], env, root).startswith("uv 0.13.9 "):
        raise ValueError("incorrect uv condition")
    raw = (FIXTURES / "specs.json").read_bytes()
    unique_json(raw)
    specs = TypeAdapter(tuple[Spec, ...]).validate_json(raw)
    (root / "identity.json").write_text(
        json.dumps(
            {
                **source_identity(),
                "distribution_sha256": distribution(prefix),
                "fixture_sha256": snapshot(FIXTURES),
                "node_sha256": digest(node.read_bytes()),
                "uv_sha256": digest(uv.read_bytes()),
                "python": platform.python_version(),
                "index": "live public PyPI; not frozen",
                "oci": "BLOCKED",
                "dependabot": "BLOCKED",
                "component": "internal; not PR generation",
            },
            indent=2,
        )
    )
    cache = root / "shared-uv-cache"
    correct = True
    for spec in specs:
        results = []
        for repetition in (1, 2):
            for arm in ARMS:
                state, files = run_arm(spec, arm, root, prefix, node, uv, cache, repetition)
                results.append(files)
                correct = correct and state == State.PASS
                print(
                    json.dumps(
                        {
                            "event": "update_adjudicated",
                            "case": spec.case_id,
                            "arm": arm,
                            "repetition": repetition,
                            "state": state,
                        }
                    ),
                    flush=True,
                )
        equal = all(result == results[0] for result in results)
        correct = correct and equal
        print(
            json.dumps(
                {"event": "matched_and_repeated_bytes", "case": spec.case_id, "equal": equal}
            ),
            flush=True,
        )
    for arm in ARMS:
        state, _ = run_arm(specs[0], arm, root, prefix, node, uv, cache, 3, True)
        correct = correct and state == State.FAIL
        print(json.dumps({"event": "conflict_control", "arm": arm, "state": state}), flush=True)
    return 0 if correct else 1


if __name__ == "__main__":
    raise SystemExit(main())
