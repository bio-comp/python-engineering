"""Bounded live component/native-uv comparison; no authenticated bot actions."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import Field, TypeAdapter, ValidationError

from experiments.e017.evidence import (
    Arm,
    EvidenceError,
    Operation,
    ProcessReceipt,
    ResolverReceipt,
    RunIdentity,
    bind_process,
    expected_environment,
    nested_timing,
    now,
    ordered,
    read_bytes,
    read_model,
    require,
)
from experiments.e017.oracle import Log, State, digest, re2_warning_allowed, unique_json
from experiments.e017.run import HERE, capture_identity, snapshot
from python_engineering.reporting.models import SHA256, Contract

FIXTURES = HERE / "update_fixtures"
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


def component_result(
    stdout: bytes, *, distribution: str = "npm-45.3.2-re2-fallback"
) -> ComponentResult:
    if not stdout.endswith(b"\n"):
        raise ValueError("truncated component log")
    result = []
    unexpected_errors = []
    for line in stdout.splitlines():
        unique_json(line)
        log = Log.model_validate_json(line)
        if log.msg == "E017 component result":
            if log.level != 30:
                raise ValueError("invalid component result severity")
            result.append(ComponentResult.model_validate_json(line))
        elif log.level >= 40 and not (
            distribution == "npm-45.3.2-re2-fallback" and re2_warning_allowed(line)
        ):
            unexpected_errors.append(log.msg)
    if len(result) != 1:
        raise ValueError("missing/duplicate component result")
    if unexpected_errors:
        raise ValueError("unexpected component warning/error")
    return result[0]


def invocation_evidence(path: Path, dependency: str, conflict: bool) -> bool:
    if not path.is_file():
        return False
    try:
        records = []
        raw = read_bytes(path)
        if not raw.endswith(b"\n"):
            return False
        for line in raw.splitlines():
            unique_json(line)
            records.append(TypeAdapter(list[str]).validate_json(line, strict=True))
    except ValueError, ValidationError:
        return False
    required = [["lock", "--check"], ["lock", "--upgrade-package", dependency]]
    if not conflict:
        required += [["lock", "--check"], ["lock"]]
    return records == required


class UpdateVerdict(Contract):
    state: State
    diagnostics: tuple[str, ...]
    after: dict[str, SHA256] = Field(min_length=1)
    repeated: dict[str, SHA256] | None = None
    expected_state: Literal["FAIL"] | None = None
    control_correct: bool | None = None
    raw_manifest_mutated: bool | None = None


def specs() -> tuple[Spec, ...]:
    raw = (FIXTURES / "specs.json").read_bytes()
    unique_json(raw)
    values = TypeAdapter(tuple[Spec, ...]).validate_json(raw)
    if not values or len({value.case_id for value in values}) != len(values):
        raise ValueError("empty or duplicate update specifications")
    return values


def inventory(files: dict[str, bytes]) -> dict[str, str]:
    return {name: digest(data) for name, data in files.items()}


def expected_transition(
    spec: Spec,
    conflict: bool,
) -> tuple[dict[str, bytes], bytes, str]:
    source = FIXTURES / spec.case_id
    initial = {
        name: (source / name).read_bytes() for name in ("pyproject.toml", "uv.lock", "sentinel.txt")
    }
    old = f'"{spec.dependency}=={spec.old_version}"'.encode()
    new = f'"{spec.dependency}=={spec.new_version}"'.encode()
    require(
        initial["pyproject.toml"].count(old) == 1 and old != new, "ambiguous frozen manifest target"
    )
    expected = initial["pyproject.toml"].replace(old, new)
    require(
        expected == (source / "expected.toml.txt").read_bytes(),
        "frozen expected manifest disagrees with exact target transition",
    )
    if conflict:
        expected = expected.replace(new, new + b", " + old)
    fixture_sha = digest(
        json.dumps(
            {
                "spec": spec.model_dump_json(),
                "initial": inventory(initial),
                "expected": digest(expected),
            },
            sort_keys=True,
        ).encode()
    )
    return initial, expected, fixture_sha


def conflict_reason(spec: Spec, diagnostic: bytes, python: str) -> bool:
    # Exact observed resolver clause, not a generic "No solution found".
    text = diagnostic.decode(errors="replace")
    expected = (
        f"Because your project depends on {spec.dependency}=={spec.new_version} "
        f"and {spec.dependency}=={spec.old_version}, we can conclude that "
        "your project's requirements are unsatisfiable."
    )
    return (
        f"Using CPython 3.14.10 interpreter at: {python}" in text.splitlines()
        and "error: No solution found when resolving dependencies" in text.splitlines()
        and f"  cause: {expected}" in text.splitlines()
    )


def conflict_correct(
    spec: Spec,
    arm: Arm,
    initial: dict[str, bytes],
    expected: bytes,
    actual: dict[str, bytes],
    attempted: dict[str, bytes],
    artifact: ComponentResult | None,
    returncode: int,
    diagnostic: bytes,
    python: str,
    resolver_exit: int,
) -> bool:
    intended = {**initial, "pyproject.toml": expected}
    if (
        attempted != intended
        or set(actual) != set(initial)
        or any(actual[name] != initial[name] for name in initial if name != "pyproject.toml")
        or actual.get("pyproject.toml") not in {initial["pyproject.toml"], expected}
        or resolver_exit != 1
        or not conflict_reason(spec, diagnostic, python)
    ):
        return False
    if arm == "native-uv":
        return returncode == resolver_exit and artifact is None
    if artifact is None or returncode != 0 or len(artifact.artifacts) != 1:
        return False
    item = artifact.artifacts[0]
    return (
        artifact.manifest.encode() == expected
        and artifact.repeatedManifest is None
        and item.file is None
        and not item.contentsPresent
        and item.error is not None
        and item.error.fileName == "uv.lock"
        and item.error.stderr.encode() == diagnostic
    )


def uv_environment(identity: RunIdentity, case: Path) -> dict[str, str]:
    return {
        **expected_environment(identity, case, shim=True),
        "UV_PYTHON": identity.python.path,
        "UV_DEFAULT_INDEX": "https://pypi.org/simple",
        "UV_CACHE_DIR": str(Path(identity.execution_root) / "shared-uv-cache"),
    }


def binding(
    identity: RunIdentity, spec: Spec, arm: Arm, repetition: int, fixture_sha: str
) -> dict[str, str | int]:
    return {
        "run_sha256": identity.fingerprint(),
        "case_id": spec.case_id,
        "repetition": repetition,
        "arm": arm,
        "fixture_sha256": fixture_sha,
    }


def wrapper_text(
    identity: RunIdentity, spec: Spec, arm: Arm, repetition: int, fixture_sha: str
) -> str:
    case = identity.case_path(f"{spec.case_id}-{arm}-{repetition}")
    values = [
        str(case),
        str(case / "fixture"),
        identity.uv.path,
        json.dumps(binding(identity, spec, arm, repetition, fixture_sha)),
        json.dumps(uv_environment(identity, case)),
    ]
    probe = str(Path(identity.source_root) / "experiments/e017/uv_probe.py")
    return (
        f"#!{identity.python.path}\nimport runpy,sys\n"
        f"sys.argv[1:1]={values!r}\n"
        f"runpy.run_path({probe!r},run_name='__main__')\n"
    )


def commands(
    identity: RunIdentity,
    spec: Spec,
    arm: Arm,
    repetition: int,
    conflict: bool,
) -> tuple[tuple[Operation, tuple[str, ...], tuple[str, ...]], ...]:
    case = identity.case_path(f"{spec.case_id}-{arm}-{repetition}")
    wrapper = str(case / "bin/uv")
    inner_update = ("lock", "--upgrade-package", spec.dependency)
    outer_update: tuple[str, ...] = (wrapper, *inner_update)
    if arm == "renovate":
        outer_update = (
            identity.node.path,
            str(Path(identity.source_root) / "experiments/e017/update_component.mjs"),
            str(Path(identity.renovate.path).parent),
            str(case / "fixture"),
            str(case / "cache"),
            spec.dependency,
            spec.old_version,
            spec.new_version,
            "conflict" if conflict else "update",
        )
    sequence: tuple[tuple[Operation, tuple[str, ...], tuple[str, ...]], ...] = (
        ("initial-check", (wrapper, "lock", "--check"), ("lock", "--check")),
        ("update", outer_update, inner_update),
    )
    if not conflict:
        sequence += (
            ("lock-check", (wrapper, "lock", "--check"), ("lock", "--check")),
            ("repeat", (wrapper, "lock"), ("lock",)),
        )
    return sequence


def invoke(
    identity: RunIdentity,
    spec: Spec,
    arm: Arm,
    repetition: Literal[1, 2, 3],
    fixture_sha: str,
    name: Operation,
    command: tuple[str, ...],
    cwd: Path,
    env: dict[str, str],
    root: Path,
) -> subprocess.CompletedProcess[bytes]:
    started_at = now()
    start = time.monotonic()
    proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, check=False, timeout=180)
    completed_at = now()
    elapsed = time.monotonic() - start
    (root / f"{name}.stdout").write_bytes(proc.stdout)
    (root / f"{name}.stderr").write_bytes(proc.stderr)
    receipt = ProcessReceipt(
        started_at=started_at,
        run_sha256=identity.fingerprint(),
        case_id=spec.case_id,
        repetition=repetition,
        arm=arm,
        operation=name,
        fixture_sha256=fixture_sha,
        command=command,
        environment=env,
        cwd=str(cwd),
        executed_at=completed_at,
        returncode=proc.returncode,
        elapsed_seconds=elapsed,
        stdout_sha256=digest(proc.stdout),
        stderr_sha256=digest(proc.stderr),
    )
    (root / f"{name}.json").write_text(receipt.model_dump_json(indent=2))
    return proc


def checked_tree(path: Path) -> dict[str, bytes]:
    if not path.is_dir():
        raise EvidenceError(State.BLOCKED, f"missing snapshot: {path.name}")
    require(not path.is_symlink(), "symlinked snapshot")
    return {name: read_bytes(path / name) for name in snapshot(path)}


def check_inventory(path: Path, actual: dict[str, bytes]) -> None:
    raw = read_bytes(path)
    unique_json(raw)
    recorded = TypeAdapter(dict[str, SHA256]).validate_json(raw, strict=True)
    require(bool(recorded) and recorded == inventory(actual), "snapshot inventory mismatch")


def replay_update(
    identity: RunIdentity,
    spec: Spec,
    arm: Arm,
    repetition: Literal[1, 2, 3],
    evidence_dir: Path,
    *,
    reconcile: bool = True,
) -> tuple[UpdateVerdict, dict[str, bytes]]:
    conflict = repetition == 3
    require(identity.stage == "updates", "wrong update run stage")
    initial, expected, fixture_sha = expected_transition(spec, conflict)
    case = identity.case_path(f"{spec.case_id}-{arm}-{repetition}")
    path = evidence_dir / case.name
    recorded_initial = checked_tree(path / "initial")
    require(recorded_initial == initial, "initial fixture differs from frozen source")
    check_inventory(path / "initial.json", recorded_initial)
    actual = checked_tree(path / "generated")
    check_inventory(path / "generated.json", actual)
    final = checked_tree(path / "fixture")
    wrapper = read_bytes(path / "bin/uv")
    require(
        wrapper == wrapper_text(identity, spec, arm, repetition, fixture_sha).encode(),
        "uv wrapper source/condition mismatch",
    )
    require(
        invocation_evidence(path / "uv-invocations.jsonl", spec.dependency, conflict),
        "incorrect uv invocation population",
    )
    sequence = commands(identity, spec, arm, repetition, conflict)
    attempts = path / "uv-attempts"
    require(
        attempts.is_dir()
        and {p.name for p in attempts.iterdir()} == {str(i) for i in range(1, len(sequence) + 1)},
        "incorrect uv attempt population",
    )

    receipts: dict[Operation, ProcessReceipt] = {}
    inner_receipts: dict[Operation, ProcessReceipt] = {}
    inner_before: dict[Operation, dict[str, bytes]] = {}
    inner_after: dict[Operation, dict[str, bytes]] = {}
    output: dict[Operation, tuple[bytes, bytes]] = {}
    inner_output: dict[Operation, tuple[bytes, bytes]] = {}
    previous = identity.executed_at
    for index, (phase, outer, inner) in enumerate(sequence, 1):
        outer_rec = read_model(path / f"{phase}.json", ProcessReceipt)
        stdout, stderr = read_bytes(path / f"{phase}.stdout"), read_bytes(path / f"{phase}.stderr")
        bind_process(
            identity,
            outer_rec,
            case_id=spec.case_id,
            repetition=repetition,
            arm=arm,
            operation=phase,
            fixture_sha=fixture_sha,
            command=outer,
            cwd=case / "fixture",
            env=expected_environment(identity, case, shim=True),
            stdout=stdout,
            stderr=stderr,
        )
        attempt = attempts / str(index)
        inner_rec = read_model(attempt / "receipt.json", ResolverReceipt)
        raw_stdout, raw_stderr = read_bytes(attempt / "stdout"), read_bytes(attempt / "stderr")
        bind_process(
            identity,
            inner_rec,
            case_id=spec.case_id,
            repetition=repetition,
            arm=arm,
            operation=phase,
            fixture_sha=fixture_sha,
            command=(identity.uv.path, *inner),
            cwd=case / "fixture",
            env=uv_environment(identity, case),
            stdout=raw_stdout,
            stderr=raw_stderr,
        )
        nested_timing(outer_rec, inner_rec)
        ordered(previous, outer_rec.started_at, "overlapping or reversed update phases")
        previous = outer_rec.executed_at
        if phase != "update" or arm == "native-uv":
            require(
                (outer_rec.returncode, stdout, stderr)
                == (inner_rec.returncode, raw_stdout, raw_stderr),
                "outer/inner uv result mismatch",
            )
        receipts[phase] = outer_rec
        inner_receipts[phase] = inner_rec
        inner_before[phase] = checked_tree(attempt / "before")
        inner_after[phase] = checked_tree(attempt / "after")
        require(
            inner_rec.before == inventory(inner_before[phase])
            and inner_rec.after == inventory(inner_after[phase]),
            "resolver receipt snapshot digest mismatch",
        )
        output[phase] = (stdout, stderr)
        inner_output[phase] = (raw_stdout, raw_stderr)
    require(
        receipts["initial-check"].returncode == 0
        and inner_before["initial-check"] == inner_after["initial-check"] == initial,
        "initial lock check failed or changed bytes",
    )
    require(
        inner_before["update"] == {**initial, "pyproject.toml": expected},
        "resolver did not attempt the expected manifest/lock population",
    )
    artifact = None
    outer_update = receipts["update"]
    if arm == "renovate":
        # Known bootstrap note is stderr, not a log-level exception.
        note = (
            "⚠️ NOTE ⚠️: Renovate's logger has not yet been initialized. "
            "If you see no other output, this is a bug\n"
        ).encode()
        require(output["update"][1] in (b"", note), "unexpected component stderr")
        if outer_update.returncode == 0:
            artifact = component_result(output["update"][0], distribution=identity.distribution)
    if conflict:
        require(
            inner_after["update"] == inner_before["update"],
            "conflict resolver changed attempted tree",
        )
        correct = conflict_correct(
            spec,
            arm,
            initial,
            expected,
            actual,
            inner_before["update"],
            artifact,
            outer_update.returncode,
            inner_output["update"][1],
            identity.python.path,
            inner_receipts["update"].returncode,
        )
        require(final == actual, "conflict final state differs from generated state")
        mutated = actual.get("pyproject.toml") != initial["pyproject.toml"]
        errors: tuple[str, ...] = (
            ("conflict correctly rejected",) if correct else ("conflict control failed",)
        )
        if mutated:
            errors += ("failed operation left staged manifest modified; not atomic",)
        verdict = UpdateVerdict(
            state=State.FAIL if correct else State.BLOCKED,
            diagnostics=errors,
            after=inventory(actual),
            expected_state="FAIL",
            control_correct=correct,
            raw_manifest_mutated=mutated,
        )
    else:
        repeated = checked_tree(path / "repeated")
        check_inventory(path / "repeated.json", repeated)
        require(
            inner_receipts["update"].returncode == 0 and inner_after["update"] == actual,
            "generated files do not match successful resolver output",
        )
        require(
            inner_before["lock-check"] == inner_after["lock-check"] == actual,
            "lock check changed bytes or checked wrong state",
        )
        require(
            inner_before["repeat"] == actual and inner_after["repeat"] == repeated == final,
            "repeated resolution evidence mismatch",
        )
        errors = update_errors(
            spec,
            initial,
            expected,
            actual,
            artifact=artifact,
            arm=arm,
            returncode=outer_update.returncode,
            lock_check_exit=receipts["lock-check"].returncode,
            repeated=repeated if receipts["repeat"].returncode == 0 else None,
        )
        verdict = UpdateVerdict(
            state=State.FAIL if errors else State.PASS,
            diagnostics=errors,
            after=inventory(actual),
            repeated=inventory(repeated),
        )
    if reconcile:
        require(
            read_model(path / "verdict.json", UpdateVerdict) == verdict,
            "saved update verdict differs from evidence replay",
        )
    return verdict, actual


def retain_tree(source: Path, case: Path, name: str) -> None:
    target = case / name
    shutil.copytree(source, target, symlinks=True)
    (case / f"{name}.json").write_text(json.dumps(snapshot(target), indent=2))


def run_arm(
    spec: Spec,
    arm: Arm,
    identity: RunIdentity,
    repetition: Literal[1, 2, 3],
) -> tuple[State, dict[str, bytes]]:
    conflict = repetition == 3
    case = identity.case_path(f"{spec.case_id}-{arm}-{repetition}")
    case.mkdir()
    fixture = case / "fixture"
    fixture.mkdir()
    initial, expected, fixture_sha = expected_transition(spec, conflict)
    for name, data in initial.items():
        (fixture / name).write_bytes(data)
    (case / "home").mkdir()
    shim = case / "bin"
    shim.mkdir()
    python = Path(identity.python.path)
    (shim / "python").symlink_to(python)
    (shim / "python3").symlink_to(python)
    wrapper = shim / "uv"
    wrapper.write_text(wrapper_text(identity, spec, arm, repetition, fixture_sha))
    wrapper.chmod(0o700)
    env = expected_environment(identity, case, shim=True)
    retain_tree(fixture, case, "initial")
    for phase, command, _ in commands(identity, spec, arm, repetition, conflict):
        if phase == "update" and arm == "native-uv":
            (fixture / "pyproject.toml").write_bytes(expected)
        invoke(identity, spec, arm, repetition, fixture_sha, phase, command, fixture, env, case)
        if phase == "update":
            retain_tree(fixture, case, "generated")
        elif phase == "repeat":
            retain_tree(fixture, case, "repeated")
    verdict, actual = replay_update(
        identity, spec, arm, repetition, Path(identity.execution_root), reconcile=False
    )
    (case / "verdict.json").write_text(verdict.model_dump_json(indent=2))
    return verdict.state, actual


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
    identity = capture_identity(root, prefix, node, uv, "updates")
    (root / "identity.json").write_text(identity.model_dump_json(indent=2))
    cases = specs()
    correct = True
    repetitions: tuple[Literal[1, 2], ...] = (1, 2)
    for spec in cases:
        results = []
        for repetition in repetitions:
            for arm in ARMS:
                state, files = run_arm(spec, arm, identity, repetition)
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
        state, _ = run_arm(cases[0], arm, identity, 3)
        correct = correct and state == State.FAIL
        print(json.dumps({"event": "conflict_control", "arm": arm, "state": state}), flush=True)
    return 0 if correct else 1


if __name__ == "__main__":
    raise SystemExit(main())
