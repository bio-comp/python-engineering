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


def extract_logs(case: Fixture, stage: Literal["extract", "lookup"]) -> bytes:
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
    raw = extract_logs(case, stage)
    rec = BoundExtraction(
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
