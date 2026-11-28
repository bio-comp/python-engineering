"""Offline end-to-end receipt/byte replay and R1 regression controls.

All generated evidence here is explicitly synthetic; real report admission must
reject it. Positive cases exercise the consumer, not the external tools.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Literal

import pytest

from experiments.e017.evidence import (
    Arm,
    BoundExtraction,
    EvidenceError,
    Executable,
    Operation,
    PolicyReceipt,
    ProcessReceipt,
    ResolverReceipt,
    RunIdentity,
    RunStage,
    expected_environment,
    log_context,
)
from experiments.e017.oracle import (
    Fixture,
    State,
    digest,
    judge_logs,
    policy_control_correct,
    re2_warning_allowed,
)
from experiments.e017.report import make_run
from experiments.e017.run import HERE, corpus, fixture_identity, source_identity
from experiments.e017.updates import (
    Artifact,
    ArtifactError,
    ComponentResult,
    Spec,
    UpdateVerdict,
    commands,
    component_result,
    expected_transition,
    inventory,
    specs,
    uv_environment,
    wrapper_text,
)
from python_engineering.reporting.cli import build_report
from python_engineering.reporting.models import Run

TIME = "2026-11-27T20:00:00+00:00"
REP = Literal[1, 2, 3]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2))


def lines(*events: dict[str, object]) -> bytes:
    return b"".join(json.dumps(event).encode() + b"\n" for event in events)


def identity(root: Path, stage: RunStage) -> RunIdentity:
    prefix = root / "synthetic-prefix"
    dist = prefix / "node_modules/renovate/dist"

    def exe(path: Path, version: str) -> Executable:
        return Executable(path=str(path), sha256=digest(str(path).encode()), version=version)

    return RunIdentity(
        stage=stage,
        source=source_identity(),
        source_root=str(HERE.parents[1]),
        execution_root=str(root / stage),
        prefix=str(prefix),
        python=exe(root / "synthetic-python", "3.14.10"),
        python_entrypoint=str(root / "synthetic-venv/bin/python"),
        node=exe(root / "synthetic-node", "v26.13.1"),
        uv=exe(root / "synthetic-uv", "uv 0.13.9 synthetic"),
        renovate=exe(dist / "renovate.js", "45.3.2"),
        validator=exe(dist / "config-validator.js", "45.3.2"),
        distribution="synthetic-control",
        distribution_sha256=digest(b"synthetic-distribution"),
        npm_lock_sha256=digest(b"synthetic-lock"),
        fixture_sha256=fixture_identity(),
        executed_at=TIME,
        platform="synthetic",
    )


def tree(path: Path, files: dict[str, bytes]) -> None:
    path.mkdir(parents=True)
    for name, data in files.items():
        item = path / name
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_bytes(data)


def extract_logs(
    case: Fixture,
    stage: Literal["extract", "lookup"],
    context: str,
    rep: int,
) -> bytes:
    managers: dict[str, dict[str, list[dict[str, object]]]] = {}
    if case.case_id != "malformed-toml":
        for dep in case.expected:
            raw: dict[str, object] = {
                "depName": dep.name,
                "packageName": dep.package or dep.name,
                "datasource": dep.datasource,
                "currentValue": dep.value,
                "currentDigest": dep.digest,
                "depType": dep.dep_type,
                "lockedVersion": dep.locked,
                "skipReason": dep.required_skip,
            }
            if stage == "lookup":
                raw.update(updates=[], warnings=[], currentVersion="test", registryUrl="synthetic")
            managers.setdefault(dep.manager, {}).setdefault(dep.file, []).append(raw)
    files = {
        m: [{"packageFile": path, "deps": deps} for path, deps in values.items()]
        for m, values in managers.items()
    }
    counts = {
        m: {"fileCount": len(v), "depCount": sum(len(d) for d in v.values())}
        for m, v in managers.items()
    }
    total = {
        "fileCount": sum(c["fileCount"] for c in counts.values()),
        "depCount": sum(c["depCount"] for c in counts.values()),
    }
    events: list[dict[str, object]] = []
    if case.case_id == "malformed-toml":
        events.append({"msg": "Failed to parse and validate pyproject file", "level": 20})
    events.extend(
        [
            {
                "msg": "Dependency extraction complete",
                "level": 20,
                "stats": {"managers": counts, "total": total},
            },
            {
                "msg": "Extracted dependencies"
                if stage == "extract"
                else "packageFiles with updates",
                "level": 20,
                "packageFiles" if stage == "extract" else "config": files,
            },
            {"msg": "Repository finished", "level": 30},
        ]
    )
    for event in events:
        if event["msg"] in {
            "Dependency extraction complete",
            "Extracted dependencies",
            "packageFiles with updates",
            "Repository finished",
        }:
            event.update(
                name="renovate",
                hostname="synthetic",
                pid=100 + rep,
                logContext=context,
                repository="local",
                time=TIME,
                v=0,
            )
            event["level"] = 20 if event["msg"] == "packageFiles with updates" else 30
    return lines(*events)


def create_extraction(
    root: Path,
    ident: RunIdentity,
    case: Fixture,
    stage: Literal["extract", "lookup"],
    rep: Literal[1, 2],
) -> None:
    path = root / ident.stage / f"{case.case_id}-{stage}-{rep}"
    path.mkdir()
    data = {name: content.encode() for name, content in case.files.items()}
    tree(path / "fixture", data)
    raw = extract_logs(case, stage, log_context(ident, path), rep)
    rec = BoundExtraction(
        started_at=TIME,
        run_sha256=ident.fingerprint(),
        repetition=rep,
        cwd=str(path / "fixture"),
        case_id=case.case_id,
        stage=stage,
        fixture_sha256=case.fingerprint(),
        distribution=ident.distribution,
        tool_version="45.3.2",
        distribution_sha256=ident.distribution_sha256,
        node_version=ident.node.version,
        python_version=ident.python.version,
        uv_version=ident.uv.version,
        command=(ident.node.path, ident.renovate.path, "--platform=local", f"--dry-run={stage}"),
        environment=expected_environment(ident, path),
        executed_at=TIME,
        returncode=0,
        elapsed_seconds=0.0,
        stdout_sha256=digest(raw),
        stderr_sha256=digest(b""),
        before=inventory(data),
        after=inventory(data),
    )
    (path / "stdout.jsonl").write_bytes(raw)
    (path / "stderr.txt").write_bytes(b"")
    (path / "receipt.json").write_text(rec.model_dump_json())
    verdict = judge_logs(case, stage, rec, raw, b"")
    (path / "verdict.json").write_text(verdict.model_dump_json())


def create_policy(root: Path, ident: RunIdentity, name: str, config: object) -> None:
    path = root / "extract" / f"policy-{name}"
    path.mkdir()
    candidate = json.dumps(config, indent=2).encode()
    (path / "candidate.json").write_bytes(candidate)
    positive = name in {"repository", "administrative"}
    event: dict[str, object]
    if positive:
        event = {"msg": "Config validated successfully against 1 file(s)", "level": 30}
    elif name == "invalid-manager":
        event = {
            "msg": "Found errors in configuration",
            "level": 50,
            "errors": [
                {
                    "topic": "Configuration Error",
                    "message": "Invalid enabledManagers: not-a-manager",
                }
            ],
        }
    else:
        event = {
            "msg": "Config migration necessary",
            "level": 40,
            "oldConfig": config,
            "newConfig": {"dependencyDashboard": {"enabled": True}}
            if name == "obsolete"
            else {"automerge": False},
        }
    raw = lines(event)
    command = (ident.node.path, ident.validator.path, "--strict")
    full_command = (
        *command,
        *(("--no-global",) if name != "administrative" else ()),
        str(path / "candidate.json"),
    )
    rec = PolicyReceipt(
        started_at=TIME,
        run_sha256=ident.fingerprint(),
        case_id=name,
        repetition=1,
        arm="renovate",
        operation="policy",
        fixture_sha256=digest(candidate),
        command=full_command,
        environment=expected_environment(ident, path),
        cwd=str(path),
        executed_at=TIME,
        returncode=0 if positive else 1,
        elapsed_seconds=0.0,
        stdout_sha256=digest(raw),
        stderr_sha256=digest(b""),
        config_sha256=digest(candidate),
        expected_valid=positive,
        control_correct=True,
        scope="schema validation only",
    )
    assert policy_control_correct(name, candidate, raw, b"", rec.returncode)
    (path / "receipt.json").write_text(rec.model_dump_json())
    (path / "stdout.jsonl").write_bytes(raw)
    (path / "stderr.txt").write_bytes(b"")


def make_process(
    ident: RunIdentity,
    spec: Spec,
    arm: Arm,
    rep: REP,
    phase: Operation,
    fixture_sha: str,
    command: tuple[str, ...],
    env: dict[str, str],
    cwd: Path,
    stdout: bytes,
    stderr: bytes,
    code: int,
) -> ProcessReceipt:
    return ProcessReceipt(
        started_at=TIME,
        run_sha256=ident.fingerprint(),
        case_id=spec.case_id,
        repetition=rep,
        arm=arm,
        operation=phase,
        fixture_sha256=fixture_sha,
        command=command,
        environment=env,
        cwd=str(cwd),
        executed_at=TIME,
        returncode=code,
        elapsed_seconds=0.0,
        stdout_sha256=digest(stdout),
        stderr_sha256=digest(stderr),
    )


def create_update(root: Path, ident: RunIdentity, spec: Spec, arm: Arm, rep: REP) -> None:
    conflict = rep == 3
    case = root / "updates" / f"{spec.case_id}-{arm}-{rep}"
    case.mkdir()
    initial, expected, fixture_sha = expected_transition(spec, conflict)
    lock = initial["uv.lock"]
    if not conflict:
        old = f'name = "{spec.dependency}"\nversion = "{spec.old_version}"'.encode()
        new = f'name = "{spec.dependency}"\nversion = "{spec.new_version}"'.encode()
        assert lock.count(old) == 1
        lock = lock.replace(old, new)
    attempted = {**initial, "pyproject.toml": expected}
    after = {**attempted, "uv.lock": lock}
    for name, files in (("initial", initial), ("generated", after), ("fixture", after)):
        tree(case / name, files)
        if name != "fixture":
            write_json(case / f"{name}.json", inventory(files))
    if not conflict:
        tree(case / "repeated", after)
        write_json(case / "repeated.json", inventory(after))
    (case / "bin").mkdir()
    (case / "bin/uv").write_text(wrapper_text(ident, spec, arm, rep, fixture_sha))
    diagnostic = (
        f"Using CPython 3.14.10 interpreter at: {ident.python.path}\n"
        "error: No solution found when resolving dependencies\n"
        f"  cause: Because your project depends on {spec.dependency}=={spec.new_version} "
        f"and {spec.dependency}=={spec.old_version}, we can conclude that "
        "your project's requirements are unsatisfiable.\n"
    ).encode()
    invocations = []
    for index, (phase, outer, inner) in enumerate(commands(ident, spec, arm, rep, conflict), 1):
        invocations.append(list(inner))
        raw_out = b""
        raw_err = diagnostic if phase == "update" and conflict else b""
        code = 1 if phase == "update" and conflict else 0
        actual_before = (
            initial if phase == "initial-check" else attempted if phase == "update" else after
        )
        actual_after = initial if phase == "initial-check" else after
        attempt = case / "uv-attempts" / str(index)
        tree(attempt / "before", actual_before)
        tree(attempt / "after", actual_after)
        (attempt / "stdout").write_bytes(raw_out)
        (attempt / "stderr").write_bytes(raw_err)
        rec = make_process(
            ident,
            spec,
            arm,
            rep,
            phase,
            fixture_sha,
            (ident.uv.path, *inner),
            uv_environment(ident, case),
            case / "fixture",
            raw_out,
            raw_err,
            code,
        )
        bound = ResolverReceipt(
            **rec.model_dump(), before=inventory(actual_before), after=inventory(actual_after)
        )
        (attempt / "receipt.json").write_text(bound.model_dump_json())
        if phase == "update" and arm == "renovate":
            artifact = Artifact(
                file=None if conflict else "uv.lock",
                error=ArtifactError(fileName="uv.lock", stderr=diagnostic.decode())
                if conflict
                else None,
                contentsPresent=not conflict,
            )
            result = ComponentResult(
                msg="E017 component result",
                level=30,
                manifest=expected.decode(),
                repeatedManifest=None if conflict else expected.decode(),
                artifacts=(artifact,),
            )
            raw_out = result.model_dump_json().encode() + b"\n"
            raw_err = b""
            code = 0
        (case / f"{phase}.stdout").write_bytes(raw_out)
        (case / f"{phase}.stderr").write_bytes(raw_err)
        rec = make_process(
            ident,
            spec,
            arm,
            rep,
            phase,
            fixture_sha,
            outer,
            expected_environment(ident, case, shim=True),
            case / "fixture",
            raw_out,
            raw_err,
            code,
        )
        (case / f"{phase}.json").write_text(rec.model_dump_json())
    (case / "uv-invocations.jsonl").write_text("".join(json.dumps(x) + "\n" for x in invocations))
    verdict = UpdateVerdict(
        state=State.FAIL if conflict else State.PASS,
        diagnostics=(
            "conflict correctly rejected",
            "failed operation left staged manifest modified; not atomic",
        )
        if conflict
        else (),
        after=inventory(after),
        repeated=None if conflict else inventory(after),
        expected_state="FAIL" if conflict else None,
        control_correct=True if conflict else None,
        raw_manifest_mutated=True if conflict else None,
    )
    (case / "verdict.json").write_text(verdict.model_dump_json())


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    root = tmp_path.resolve() / "bundle"
    ex, lo, up = identity(root, "extract"), identity(root, "lookup"), identity(root, "updates")
    for ident in (ex, lo, up):
        path = Path(ident.execution_root)
        path.mkdir(parents=True)
        filename = "identity.json" if ident.stage == "updates" else "run-identity.json"
        (path / filename).write_text(ident.model_dump_json())
    tree(
        root / "extract/expected-inputs",
        {name: (HERE / name).read_bytes() for name in fixture_identity()},
    )
    for case in corpus():
        create_extraction(root, ex, case, "extract", 1)
        create_extraction(root, ex, case, "extract", 2)
    create_extraction(root, lo, corpus()[0], "lookup", 1)
    for name, config in json.loads((HERE / "policies.json").read_bytes()).items():
        create_policy(root, ex, name, config)
    arms: tuple[Arm, ...] = ("renovate", "native-uv")
    for spec in specs():
        for arm in arms:
            create_update(root, up, spec, arm, 1)
            create_update(root, up, spec, arm, 2)
    for arm in arms:
        create_update(root, up, specs()[0], arm, 3)
    return root


def report(root: Path, *, synthetic: bool = True) -> Run:
    return make_run(
        root,
        root / "extract",
        root / "lookup",
        root / "updates",
        "offline-r1-control",
        allow_synthetic=synthetic,
    )


def gate(run: Run, name: str) -> bool | None:
    return next(g.passed for g in run.gates if g.gate_id == name)


def change(path: Path, **fields: object) -> None:
    data = json.loads(path.read_bytes())
    data.update(fields)
    write_json(path, data)


def test_complete_persisted_evidence(bundle: Path) -> None:
    run = report(bundle)
    assert run.synthetic_demonstration
    for name in ("extraction", "lookup", "configuration", "updates"):
        assert gate(run, name) is True
    assert gate(run, "oci") is None
    input_file = bundle / "synthetic-input.json"
    input_file.write_text(run.model_dump_json())
    output = build_report(input_file, bundle / "synthetic-report", evidence_root=bundle)
    assert json.loads(output.read_bytes())["synthetic_demonstration"] is True
    with pytest.raises(EvidenceError, match="synthetic evidence"):
        report(bundle, synthetic=False)


@pytest.mark.parametrize(
    "variant",
    [
        "missing-update",
        "empty-after",
        "missing-repeat",
        "bad-stdout",
        "wrong-file",
        "wrong-attempt",
        "wrong-inner-inventory",
        "missing-lock-check",
        "missing-inner",
        "wrong-command",
        "wrong-timestamp",
        "wrong-case",
        "wrong-arm",
        "wrong-fixture",
        "missing-wrapper",
    ],
)
def test_update_evidence_rejected(bundle: Path, variant: str) -> None:
    case = bundle / "updates/requests-regression-renovate-1"
    if variant == "missing-update":
        (case / "update.json").unlink()
    elif variant == "empty-after":
        change(case / "verdict.json", after={})
    elif variant == "missing-repeat":
        shutil.rmtree(case / "repeated")
    elif variant == "bad-stdout":
        (case / "update.stdout").write_bytes(b"wrong output")
    elif variant == "wrong-file":
        (case / "generated/sentinel.txt").write_bytes(b"mutated unrelated file")
    elif variant == "wrong-attempt":
        (case / "uv-attempts/2/before/pyproject.toml").write_bytes(b"wrong input")
    elif variant == "wrong-inner-inventory":
        change(case / "uv-attempts/2/receipt.json", before={})
    elif variant == "missing-lock-check":
        (case / "lock-check.json").unlink()
    elif variant == "missing-inner":
        shutil.rmtree(case / "uv-attempts/2")
    elif variant == "wrong-command":
        change(case / "update.json", command=["synthetic unrelated command"])
    elif variant == "wrong-timestamp":
        change(case / "update.json", executed_at="not a datetime")
    elif variant == "wrong-case":
        change(case / "update.json", case_id="other")
    elif variant == "wrong-arm":
        change(case / "update.json", arm="native-uv")
    elif variant == "wrong-fixture":
        change(case / "update.json", fixture_sha256="0" * 64)
    else:
        (case / "bin/uv").unlink()
    with pytest.raises(EvidenceError):
        report(bundle)


def change_lock_bytes(case: Path) -> None:
    # Preserve name/version oracle, lock receipt results and internal repeat,
    # but deliberately vary otherwise irrelevant lock bytes.
    paths = [
        "generated",
        "fixture",
        "repeated",
        "uv-attempts/2/after",
        "uv-attempts/3/before",
        "uv-attempts/3/after",
        "uv-attempts/4/before",
        "uv-attempts/4/after",
    ]
    for name in paths:
        path = case / name / "uv.lock"
        path.write_bytes(path.read_bytes() + b"\n# alternative lock bytes\n")
    h = digest((case / "generated/uv.lock").read_bytes())
    for name in ("generated", "repeated"):
        data = json.loads((case / f"{name}.json").read_bytes())
        data["uv.lock"] = h
        write_json(case / f"{name}.json", data)
    for number in (2, 3, 4):
        receipt = case / f"uv-attempts/{number}/receipt.json"
        data = json.loads(receipt.read_bytes())
        data["after"]["uv.lock"] = h
        if number != 2:
            data["before"]["uv.lock"] = h
        write_json(receipt, data)
    verdict = json.loads((case / "verdict.json").read_bytes())
    verdict["after"]["uv.lock"] = h
    verdict["repeated"]["uv.lock"] = h
    write_json(case / "verdict.json", verdict)


@pytest.mark.parametrize("both_arms", [False, True])
def test_matched_and_repeated_bytes(bundle: Path, both_arms: bool) -> None:
    change_lock_bytes(bundle / "updates/requests-regression-renovate-2")
    if both_arms:
        change_lock_bytes(bundle / "updates/requests-regression-native-uv-2")
    assert gate(report(bundle), "updates") is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("distribution", "npm-45.3.2-re2-fallback"),
        ("distribution_sha256", "0" * 64),
        ("node_version", "v0"),
        ("python_version", "0"),
        ("uv_version", "uv 0"),
        ("command", ["unrelated"]),
        ("executed_at", "not a datetime"),
        ("repetition", 2),
        ("environment", {"HOME": "/wrong"}),
        ("cwd", "/wrong"),
    ],
)
def test_extraction_binding(bundle: Path, field: str, value: object) -> None:
    change(bundle / "extract/mixed-extraction-extract-1/receipt.json", **{field: value})
    with pytest.raises(EvidenceError):
        report(bundle)


@pytest.mark.parametrize(
    "variant",
    [
        "empty-command",
        "empty-env",
        "wrong-validity",
        "wrong-mode",
        "missing",
        "wrong-config",
        "wrong-time",
    ],
)
def test_policy_binding(bundle: Path, variant: str) -> None:
    path = bundle / "extract/policy-repository/receipt.json"
    if variant == "empty-command":
        change(path, command=[])
    elif variant == "empty-env":
        change(path, environment={})
    elif variant == "wrong-validity":
        change(path, expected_valid=False)
    elif variant == "wrong-mode":
        data = json.loads(path.read_bytes())
        change(path, command=[arg for arg in data["command"] if arg != "--no-global"])
    elif variant == "missing":
        path.unlink()
    elif variant == "wrong-config":
        change(path, config_sha256="0" * 64)
    else:
        change(path, executed_at="not a datetime")
    with pytest.raises(EvidenceError):
        report(bundle)


@pytest.mark.parametrize("variant", ["wrong-reason", "extra-file", "wrong-manifest"])
@pytest.mark.parametrize("arm", ["renovate", "native-uv"])
def test_conflict_invariants(bundle: Path, variant: str, arm: Arm) -> None:
    case = bundle / "updates" / f"requests-regression-{arm}-3"
    if variant == "wrong-reason":
        error = b"No solution found for unrelated reason\n"
        (case / "uv-attempts/2/stderr").write_bytes(error)
        change(case / "uv-attempts/2/receipt.json", stderr_sha256=digest(error))
        if arm == "native-uv":
            (case / "update.stderr").write_bytes(error)
            change(case / "update.json", stderr_sha256=digest(error))
        else:
            raw = json.loads((case / "update.stdout").read_bytes())
            raw["artifacts"][0]["error"]["stderr"] = error.decode()
            stdout = json.dumps(raw).encode() + b"\n"
            (case / "update.stdout").write_bytes(stdout)
            change(case / "update.json", stdout_sha256=digest(stdout))
    else:
        name = "extra.txt" if variant == "extra-file" else "pyproject.toml"
        for folder in ("generated", "fixture"):
            (case / folder / name).write_bytes(b"unexpected bytes")
        for file in ("generated.json", "verdict.json"):
            raw = json.loads((case / file).read_bytes())
            if file == "generated.json":
                raw[name] = digest(b"unexpected bytes")
            else:
                raw["after"][name] = digest(b"unexpected bytes")
            write_json(case / file, raw)
    with pytest.raises(EvidenceError):
        report(bundle)


@pytest.mark.parametrize(
    "message",
    [
        "RE2 not usable, falling back to RegExp",
        "GitHub token is required for some dependencies",
    ],
)
def test_fatal_diagnostics_rejected(bundle: Path, message: str) -> None:
    path = bundle / "extract/mixed-extraction-extract-1"
    raw = (path / "stdout.jsonl").read_bytes()
    event = {
        "msg": message,
        "level": 60,
        "repository": "local",
        "githubDeps": ["actions/checkout"],
        "err": {
            "code": "MODULE_NOT_FOUND",
            "message": "Cannot find module './build/Release/re2.node'",
            "requireStack": ["/synthetic/re2/re2.js"],
        },
    }
    raw = lines(event) + raw
    (path / "stdout.jsonl").write_bytes(raw)
    change(path / "receipt.json", stdout_sha256=digest(raw))
    with pytest.raises(EvidenceError):
        report(bundle)


def test_structured_re2_exception_scope() -> None:
    message = "RE2 not usable, falling back to RegExp"
    raw = {
        "msg": message,
        "level": 40,
        "err": {
            "code": "MODULE_NOT_FOUND",
            "message": "Cannot find module './build/Release/re2.node'",
            "requireStack": ["/synthetic/re2/re2.js"],
        },
    }
    assert re2_warning_allowed(json.dumps(raw).encode())
    assert not re2_warning_allowed(json.dumps({**raw, "level": 60}).encode())
    assert not re2_warning_allowed(json.dumps({"msg": message, "level": 40}).encode())
    raw["msg"] = message + ": regex validation may be inaccurate"
    assert re2_warning_allowed(json.dumps(raw).encode(), policy=True)
    assert not re2_warning_allowed(json.dumps(raw).encode())


def test_fatal_component_conflict_is_not_exempt(bundle: Path) -> None:
    path = bundle / "updates/requests-regression-renovate-3/update.stdout"
    raw = path.read_bytes()
    assert component_result(raw).artifacts[0].error is not None
    fatal = lines({"msg": "RE2 not usable, falling back to RegExp", "level": 60})
    with pytest.raises(ValueError):
        component_result(fatal + raw)


@pytest.mark.parametrize(
    "variant",
    [
        "spliced",
        "pid",
        "context",
        "missing-context",
        "repository",
        "reversed-time",
        "outside-time",
    ],
)
def test_material_log_context_regression(bundle: Path, variant: str) -> None:
    path = bundle / "extract/mixed-extraction-extract-1"
    events = [json.loads(line) for line in (path / "stdout.jsonl").read_bytes().splitlines()]
    payload = next(event for event in events if event["msg"] == "Extracted dependencies")
    if variant == "spliced":
        other = path.parent / "mixed-extraction-extract-2/stdout.jsonl"
        replacement = next(
            json.loads(line)
            for line in other.read_bytes().splitlines()
            if json.loads(line)["msg"] == "Extracted dependencies"
        )
        payload.clear()
        payload.update(replacement)
    elif variant == "pid":
        payload["pid"] += 1
    elif variant == "context":
        payload["logContext"] = "other-invocation"
    elif variant == "missing-context":
        del payload["logContext"]
    elif variant == "repository":
        payload["repository"] = "other"
    elif variant == "reversed-time":
        payload["time"] = "2026-11-27T19:59:59Z"
    else:
        for event in events:
            if "time" in event:
                event["time"] = "2099-01-01T00:00:00Z"
    raw = lines(*events)
    (path / "stdout.jsonl").write_bytes(raw)
    change(path / "receipt.json", stdout_sha256=digest(raw))
    with pytest.raises(EvidenceError):
        report(bundle)


@pytest.mark.parametrize(
    "variant",
    [
        "future-child",
        "child-before-parent",
        "reversed-parent",
        "overlap",
        "before-run",
        "cross-case",
        "cross-stage",
        "missing-start",
    ],
)
def test_receipt_chronology_regression(bundle: Path, variant: str) -> None:
    path = bundle / "updates/requests-regression-renovate-1"
    if variant == "future-child":
        change(path / "uv-attempts/3/receipt.json", executed_at="2099-01-01T00:00:00Z")
    elif variant == "child-before-parent":
        change(path / "uv-attempts/2/receipt.json", started_at="2026-11-27T19:59:59Z")
    elif variant == "reversed-parent":
        change(path / "update.json", started_at="2026-11-27T20:00:02Z")
    elif variant in {"overlap", "cross-case"}:
        phase, index = ("update", 2) if variant == "overlap" else ("repeat", 4)
        for receipt in (path / f"{phase}.json", path / f"uv-attempts/{index}/receipt.json"):
            change(receipt, executed_at="2026-11-27T20:00:03Z")
    elif variant == "before-run":
        change(path / "initial-check.json", started_at="2026-11-27T19:59:59Z")
    elif variant == "cross-stage":
        change(
            bundle / "lookup/mixed-extraction-lookup-1/receipt.json",
            executed_at="2026-11-27T20:01:00Z",
        )
    else:
        receipt = path / "initial-check.json"
        raw = json.loads(receipt.read_bytes())
        del raw["started_at"]
        write_json(receipt, raw)
    with pytest.raises(EvidenceError):
        report(bundle)


def test_valid_nested_timing(bundle: Path) -> None:
    # The final case can finish later than the synthetic zero-duration predecessors.
    path = bundle / "updates/requests-regression-native-uv-3"
    for phase, index, second in (("initial-check", 1, 1), ("update", 2, 3)):
        stamp = f"2026-11-27T20:00:{second:02d}"
        change(path / f"{phase}.json", started_at=stamp + "Z", executed_at=stamp + ".900Z")
        change(
            path / f"uv-attempts/{index}/receipt.json",
            started_at=stamp + ".100Z",
            executed_at=stamp + ".800Z",
        )
    assert gate(report(bundle), "updates") is True


@pytest.mark.parametrize(
    ("case_name", "message", "level"),
    [
        ("obsolete", "Config migration necessary", 60),
        ("invalid-type", "Config migration necessary", 50),
        ("invalid-manager", "Found errors in configuration", 60),
        ("invalid-manager", "Found errors in configuration", 40),
        ("repository", "Config validated successfully against 1 file(s)", 20),
        ("repository", "Config validated successfully against 1 file(s)", 60),
    ],
)
def test_policy_exact_severity(bundle: Path, case_name: str, message: str, level: int) -> None:
    path = bundle / f"extract/policy-{case_name}"
    events = [json.loads(line) for line in (path / "stdout.jsonl").read_bytes().splitlines()]
    for event in events:
        if event["msg"] == message:
            event["level"] = level
    raw = lines(*events)
    (path / "stdout.jsonl").write_bytes(raw)
    change(path / "receipt.json", stdout_sha256=digest(raw))
    with pytest.raises(EvidenceError):
        report(bundle)


@pytest.mark.parametrize(
    "variant",
    [
        "resolver-receipt",
        "raw-log",
        "intermediate",
        "altered",
        "normalized-only",
        "no-root",
    ],
)
def test_required_report_population(bundle: Path, tmp_path: Path, variant: str) -> None:
    from python_engineering.reporting.integrity import (
        ReceiptStatus,
        assert_required_replay,
        verify_receipts,
    )

    run = report(bundle)
    aggregate = next(e for e in run.evidence if e.replay_manifest is not None)
    assert aggregate.replay_manifest is not None
    members = aggregate.replay_manifest.members
    assert len(members) > 700
    assert "extract/expected-inputs/corpus.json" in members
    assert "updates/requests-regression-renovate-1/uv-attempts/3/receipt.json" in members
    checks = verify_receipts(run, evidence_root=bundle)
    assert next(c for c in checks if c.evidence_id == aggregate.evidence_id).status == (
        ReceiptStatus.REPLAY_VERIFIED
    )
    assert_required_replay(run, checks)
    source = tmp_path / "frozen-run.json"
    source.write_text(run.model_dump_json())
    if variant == "normalized-only":
        stripped = tmp_path / "stripped"
        stripped.mkdir()
        for item in run.evidence:
            target = stripped / item.source
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundle / item.source, target)
        evidence_root: Path | None = stripped
    elif variant == "no-root":
        evidence_root = None
    else:
        evidence_root = bundle
        case = bundle / "updates/requests-regression-renovate-1"
        if variant == "resolver-receipt":
            (case / "uv-attempts/3/receipt.json").unlink()
        elif variant == "raw-log":
            (bundle / "extract/mixed-extraction-extract-1/stdout.jsonl").unlink()
        elif variant == "intermediate":
            (case / "generated/uv.lock").unlink()
        else:
            (case / "uv-attempts/3/stderr").write_bytes(b"changed after report")
    checks = verify_receipts(run, evidence_root=evidence_root)
    assert next(c for c in checks if c.evidence_id == aggregate.evidence_id).status != (
        ReceiptStatus.REPLAY_VERIFIED
    )
    with pytest.raises(ValueError):
        assert_required_replay(run, checks)
    with pytest.raises(ValueError):
        build_report(source, tmp_path / "must-not-publish", evidence_root=evidence_root)
    assert not (tmp_path / "must-not-publish").exists()


def test_real_uv_probe_lifecycle(tmp_path: Path) -> None:
    """Actual child process, local files only; no uv or package index invocation."""
    import os
    import subprocess
    import sys
    from datetime import UTC, datetime

    root = tmp_path.resolve() / "probe"
    fixture = root / "fixture"
    tree(fixture, {"sentinel.txt": b"before"})
    context = {
        "run_sha256": digest(b"synthetic"),
        "case_id": "isolated-probe",
        "repetition": 1,
        "arm": "native-uv",
        "fixture_sha256": digest(b"fixture"),
    }
    env = {"PATH": os.defpath}
    script = (
        "from pathlib import Path; import sys; "
        "Path('sentinel.txt').write_bytes(b'after'); "
        "print('child stdout'); print('child stderr', file=sys.stderr); sys.exit(7)"
    )
    command = [
        sys.executable,
        str(HERE / "uv_probe.py"),
        str(root),
        str(fixture),
        sys.executable,
        json.dumps(context),
        json.dumps(env),
        "-c",
        script,
    ]
    before = datetime.now(UTC)
    proc = subprocess.run(command, cwd=fixture, capture_output=True, check=False)
    after = datetime.now(UTC)
    path = root / "uv-attempts/1"
    rec = ResolverReceipt.model_validate_json((path / "receipt.json").read_bytes())
    assert proc.returncode == rec.returncode == 7
    assert (
        before
        <= datetime.fromisoformat(rec.started_at)
        <= (datetime.fromisoformat(rec.executed_at))
        <= after
    )
    assert rec.before == {"sentinel.txt": digest(b"before")}
    assert rec.after == {"sentinel.txt": digest(b"after")}
    assert (path / "before/sentinel.txt").read_bytes() == b"before"
    assert (path / "after/sentinel.txt").read_bytes() == b"after"
    assert rec.stdout_sha256 == digest(proc.stdout) == digest((path / "stdout").read_bytes())
    assert rec.stderr_sha256 == digest(proc.stderr) == digest((path / "stderr").read_bytes())
    assert rec.command == (sys.executable, "-c", script)
    assert json.loads((root / "uv-invocations.jsonl").read_text()) == ["-c", script]


def expected_v3_paths() -> set[str]:
    """Independent path oracle from frozen fixture inputs, not observed directories."""
    paths = {"extract/run-identity.json", "lookup/run-identity.json", "updates/identity.json"}
    paths.update(f"extract/expected-inputs/{name}" for name in fixture_identity())

    def extraction_paths(case: Fixture, stage: str, repetition: int) -> None:
        prefix = f"{stage}/{case.case_id}-{stage}-{repetition}"
        paths.update(
            f"{prefix}/{name}"
            for name in (
                "receipt.json",
                "stdout.jsonl",
                "stderr.txt",
                "verdict.json",
            )
        )
        paths.update(f"{prefix}/fixture/{name}" for name in case.files)

    for case in corpus():
        for rep in (1, 2):
            extraction_paths(case, "extract", rep)
    extraction_paths(corpus()[0], "lookup", 1)
    for policy in json.loads((HERE / "policies.json").read_bytes()):
        paths.update(
            f"extract/policy-{policy}/{name}"
            for name in (
                "receipt.json",
                "candidate.json",
                "stdout.jsonl",
                "stderr.txt",
            )
        )
    for index, spec in enumerate(specs()):
        for rep in (1, 2, 3) if index == 0 else (1, 2):
            conflict = rep == 3
            for arm in ("renovate", "native-uv"):
                prefix = f"updates/{spec.case_id}-{arm}-{rep}"
                initial, _, _ = expected_transition(spec, conflict)
                paths.update(
                    f"{prefix}/{name}"
                    for name in (
                        "initial.json",
                        "generated.json",
                        "verdict.json",
                        "uv-invocations.jsonl",
                        "bin/uv",
                    )
                )
                states: tuple[str, ...] = ("initial", "generated", "fixture")
                phases: tuple[str, ...] = ("initial-check", "update")
                if not conflict:
                    states += ("repeated",)
                    phases += ("lock-check", "repeat")
                    paths.add(f"{prefix}/repeated.json")
                paths.update(f"{prefix}/{state}/{name}" for state in states for name in initial)
                for i, phase in enumerate(phases, 1):
                    paths.update(
                        f"{prefix}/{phase}.{suffix}" for suffix in ("json", "stdout", "stderr")
                    )
                    attempt = f"{prefix}/uv-attempts/{i}"
                    paths.update(
                        f"{attempt}/{name}" for name in ("receipt.json", "stdout", "stderr")
                    )
                    paths.update(
                        f"{attempt}/{state}/{name}"
                        for state in ("before", "after")
                        for name in initial
                    )
    return paths


def test_v3_required_population_from_frozen_spec(bundle: Path) -> None:
    from python_engineering.reporting.integrity import ReceiptStatus, verify_receipts

    run = report(bundle)
    aggregate = next(e for e in run.evidence if e.replay_manifest is not None)
    assert aggregate.replay_manifest is not None
    expected = expected_v3_paths()
    assert set(aggregate.replay_manifest.members) == expected
    assert len(expected) == 754
    assert (
        next(
            check.status
            for check in verify_receipts(run, evidence_root=bundle)
            if check.evidence_id == aggregate.evidence_id
        )
        == ReceiptStatus.REPLAY_VERIFIED
    )


@pytest.mark.parametrize(
    "variant",
    [
        "omitted-field",
        "omitted-aggregate",
        "normalized-only-map",
        "same-count-substitution",
        "inconsistent-reference",
        "unlinked-gate",
    ],
)
def test_v3_manifest_contract_cannot_be_projected_away(
    bundle: Path,
    tmp_path: Path,
    variant: str,
) -> None:
    from python_engineering.reporting.cli import main
    from python_engineering.reporting.integrity import verify_receipts

    run = report(bundle)
    data = json.loads(run.model_dump_json())
    aggregate = next(e for e in data["evidence"] if e.get("replay_manifest"))
    members = aggregate["replay_manifest"]["members"]
    evidence_root = bundle
    if variant in {"omitted-field", "omitted-aggregate", "normalized-only-map"}:
        evidence_root = tmp_path / "stripped"
        for item in run.evidence:
            target = evidence_root / item.source
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundle / item.source, target)
        if variant == "omitted-field":
            del aggregate["replay_manifest"]
        elif variant == "omitted-aggregate":
            data["evidence"].remove(aggregate)
            for gate_row in data["gates"]:
                gate_row["evidence_ids"] = [
                    ref for ref in gate_row["evidence_ids"] if ref != aggregate["evidence_id"]
                ]
        else:
            aggregate["replay_manifest"]["members"] = {
                e.source: e.source_sha256 for e in run.evidence
            }
    elif variant == "same-count-substitution":
        missing = "updates/requests-regression-renovate-1/uv-attempts/3/receipt.json"
        (bundle / missing).unlink()
        del members[missing]
        substitute = "updates/requests-regression-renovate-1/uv-attempts/3/unrelated.json"
        (bundle / substitute).write_bytes(b"irrelevant")
        members[substitute] = digest(b"irrelevant")
        assert len(members) == 754
    elif variant == "inconsistent-reference":
        data["evidence"][1]["source_sha256"] = digest(b"not the manifest digest")
    else:
        next(g for g in data["gates"] if g["gate_id"] == "updates")["evidence_ids"].remove(
            aggregate["evidence_id"]
        )
    source = tmp_path / "projected-input.json"
    write_json(source, data)
    projected = Run.model_validate_json(source.read_bytes())
    with pytest.raises(ValueError, match="E-017 v3"):
        verify_receipts(projected, evidence_root=evidence_root)
    with pytest.raises(ValueError, match="E-017 v3"):
        main(["validate-run", str(source), "--evidence-root", str(evidence_root)])
    with pytest.raises(ValueError, match="E-017 v3"):
        build_report(source, tmp_path / "must-not-publish", evidence_root=evidence_root)
    assert not (tmp_path / "must-not-publish").exists()


def test_v3_manifest_population_is_independent_of_stage_directory_names(
    bundle: Path,
    tmp_path: Path,
) -> None:
    from python_engineering.reporting.integrity import (
        ReceiptStatus,
        assert_required_replay,
        verify_receipts,
    )

    run = report(bundle)
    data = json.loads(run.model_dump_json())
    aggregate = next(e for e in data["evidence"] if e.get("replay_manifest"))
    destination = tmp_path / "relocated"
    stages = {"extract": "nested/a", "lookup": "nested/b", "updates": "nested/c"}

    def relocated(name: str) -> str:
        stage, relative = name.split("/", 1)
        return f"{stages[stage]}/{relative}"

    members = aggregate["replay_manifest"]["members"]
    for name in members:
        target = destination / relocated(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundle / name, target)
    aggregate["replay_manifest"]["members"] = {
        relocated(name): sha for name, sha in members.items()
    }
    for item in data["evidence"]:
        item["source"] = relocated(item["source"])
    moved = Run.model_validate_json(json.dumps(data))
    checks = verify_receipts(moved, evidence_root=destination)
    assert_required_replay(moved, checks)
    assert next(
        check.status for check in checks if check.evidence_id == aggregate["evidence_id"]
    ) == (ReceiptStatus.REPLAY_VERIFIED)
