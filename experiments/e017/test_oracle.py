"""Offline known-good and known-bad controls (never execute external tools)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from experiments.e017.oracle import (
    Fixture,
    Receipt,
    Stage,
    State,
    digest,
    judge_logs,
    load_fixtures,
)

HERE = Path(__file__).resolve().parent


def sample() -> Fixture:
    return Fixture.model_validate_json(
        b'{"case_id":"control","files":{"requirements.txt":"idna==3.9\\n"},'
        b'"expected":[{"manager":"pip_requirements","file":"requirements.txt",'
        b'"name":"idna","datasource":"pypi","value":"==3.9"}],'
        b'"excluded":["excluded"],"notes":"independent synthetic positive"}'
    )


def logs(stage: Stage = "extract") -> list[dict[str, object]]:
    entry = {
        "depName": "idna",
        "packageName": "idna",
        "datasource": "pypi",
        "currentValue": "==3.9",
    }
    if stage == "lookup":
        entry.update(currentVersion="3.9", registryUrl="https://pypi.org/pypi")
    dep: dict[str, object] = dict(entry)
    if stage == "lookup":
        dep["updates"] = [{"newVersion": "3.10", "newValue": "==3.10"}]
        dep["warnings"] = []
    return [
        {
            "msg": "Dependency extraction complete",
            "level": 20,
            "stats": {
                "managers": {"pip_requirements": {"fileCount": 1, "depCount": 1}},
                "total": {"fileCount": 1, "depCount": 1},
            },
        },
        {
            "msg": "Extracted dependencies" if stage == "extract" else "packageFiles with updates",
            "level": 20,
            "packageFiles" if stage == "extract" else "config": {
                "pip_requirements": [{"packageFile": "requirements.txt", "deps": [dep]}]
            },
        },
        {"msg": "Repository finished", "level": 30},
    ]


def encode(events: list[dict[str, object]]) -> bytes:
    return b"".join(json.dumps(e).encode() + b"\n" for e in events)


def receipt(stdout: bytes, stage: Stage, stderr: bytes = b"") -> Receipt:
    case = sample()
    files = {name: digest(content.encode()) for name, content in case.files.items()}
    return Receipt(
        case_id=case.case_id,
        stage=stage,
        fixture_sha256=case.fingerprint(),
        distribution="synthetic-control",
        tool_version="45.3.2",
        distribution_sha256="0" * 64,
        node_version="v26.13.1",
        python_version="3.14.10",
        uv_version="uv 0.13.9",
        command=("synthetic-control",),
        environment={"HOME": "synthetic"},
        executed_at="2026-11-27T00:00:00Z",
        returncode=0,
        elapsed_seconds=0.0,
        stdout_sha256=digest(stdout),
        stderr_sha256=digest(stderr),
        before=files,
        after=files,
    )


def check(events: list[dict[str, object]], stage: Stage = "extract") -> State:
    raw = encode(events)
    return judge_logs(sample(), stage, receipt(raw, stage), raw, b"").state


def mutate(stage: Stage, key: str, value: object) -> list[dict[str, object]]:
    events = logs(stage)
    # Deliberately mutate raw wire JSON, not the normalized observation model.
    payload = json.loads(json.dumps(events[1]))
    payload["packageFiles" if stage == "extract" else "config"]["pip_requirements"][0]["deps"][0][
        key
    ] = value
    events[1] = payload
    return events


@pytest.mark.parametrize("stage", ["extract", "lookup"])
def test_positive(stage: Stage) -> None:
    assert check(logs(stage), stage) == State.PASS


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("depName", "wrong"),
        ("packageName", "wrong"),
        ("datasource", "docker"),
        ("currentValue", "==3.8"),
        ("lockedVersion", "3.8"),
        ("skipReason", "unsupported"),
        ("depName", "excluded"),
        ("packageName", None),
        ("currentDigest", "unexpected"),
        ("depType", "wrong"),
    ],
)
def test_wrong_dependency(key: str, value: object) -> None:
    assert check(mutate("extract", key, value)) == State.FAIL


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("skipReason", "github-token-required"),
        ("warnings", [{"message": "failed"}]),
        ("updates", None),
        ("updates", [{"newValue": "==3.10"}]),
        ("currentVersion", None),
        ("registryUrl", None),
    ],
)
def test_incomplete_lookup(key: str, value: object) -> None:
    assert check(mutate("lookup", key, value), "lookup") == State.FAIL


@pytest.mark.parametrize("variant", ["empty", "missing", "duplicate", "file", "unexpected"])
def test_inventory_failures(variant: str) -> None:
    events = logs()
    wire = json.loads(json.dumps(events))
    deps = wire[1]["packageFiles"]["pip_requirements"][0]["deps"]
    if variant in {"empty", "missing"}:
        deps.clear()
    elif variant == "duplicate":
        deps.append(copy.deepcopy(deps[0]))
    elif variant == "unexpected":
        deps.append({**deps[0], "depName": "extra", "packageName": "extra"})
    else:
        wire[1]["packageFiles"]["pip_requirements"][0]["packageFile"] = "other.txt"
    # Keep the summary consistent, so it cannot be the only detection signal.
    wire[0]["stats"]["total"]["depCount"] = len(deps)
    wire[0]["stats"]["managers"]["pip_requirements"]["depCount"] = len(deps)
    assert check(wire) == State.FAIL


@pytest.mark.parametrize(
    "variant",
    ["missing", "duplicate", "reordered", "malformed", "truncated", "duplicate-key", "nonfinite"],
)
def test_protocol(variant: str) -> None:
    events = logs()
    raw = encode(events)
    if variant == "missing":
        raw = encode(events[:-1])
    elif variant == "duplicate":
        raw = encode([*events, events[1]])
    elif variant == "reordered":
        raw = encode(list(reversed(events)))
    elif variant == "malformed":
        raw += b"not JSON\n"
    elif variant == "truncated":
        raw = raw[:-2]
    elif variant == "duplicate-key":
        raw = raw.replace(b'"level": 20', b'"level": 20, "level": 20', 1)
    else:
        raw = raw.replace(b'"level": 20', b'"level": NaN', 1)
    assert judge_logs(sample(), "extract", receipt(raw, "extract"), raw, b"").state == State.FAIL


@pytest.mark.parametrize(
    "message",
    [
        "Failed to parse and validate pyproject file",
        "Failed to look up pypi package idna: no-result",
        "Datasource unknown error",
        "artifactError",
    ],
)
def test_zero_exit_error(message: str) -> None:
    events = logs()
    events.insert(1, {"msg": message, "level": 20})
    assert check(events) == State.FAIL


def test_missing_or_unbound_evidence() -> None:
    raw = encode(logs())
    rec = receipt(raw, "extract")
    assert judge_logs(sample(), "extract", None, raw, b"").state == State.BLOCKED
    changes: tuple[dict[str, object], ...] = (
        {"returncode": 1},
        {"fixture_sha256": "0" * 64},
        {"stdout_sha256": "0" * 64},
        {"after": {}},
        {"before": {}},
    )
    for change in changes:
        modified = rec.model_copy(update=change)
        assert judge_logs(sample(), "extract", modified, raw, b"").state == State.FAIL
    assert (
        judge_logs(sample(), "extract", receipt(raw, "extract", b"error"), raw, b"error").state
        == State.FAIL
    )


@given(st.text(min_size=1).filter(lambda x: x != "idna"))
def test_unexpected_identity_never_passes(name: str) -> None:
    assert check(mutate("extract", "depName", name)) == State.FAIL


def test_frozen_corpus() -> None:
    cases = load_fixtures(HERE / "corpus.json")
    assert [case.case_id for case in cases] == [
        "mixed-extraction",
        "precommit-disabled",
        "git-source",
        "malformed-toml",
        "transitive-alert-extraction",
        "unsupported-path",
    ]
    assert len(cases[0].expected) == 15
    assert len({case.fingerprint() for case in cases}) == 6


def test_digest_only_lookup_is_valid() -> None:
    events = mutate("lookup", "updates", [{"newDigest": "sha256:" + "a" * 64}])
    assert check(events, "lookup") == State.PASS


def test_malformed_control_does_not_credit_unrelated_failure() -> None:
    from experiments.e017.oracle import Verdict, extraction_control_correct

    verdict = Verdict(
        case_id="malformed-toml",
        stage="extract",
        state=State.FAIL,
        diagnostics=("nonzero exit or unexpected stderr",),
    )
    assert not extraction_control_correct(verdict)
    genuine = verdict.model_copy(
        update={
            "diagnostics": (
                "diagnostic: Failed to parse and validate pyproject file",
                "empty inventory",
                "missing or unexpected dependency identities",
            )
        }
    )
    assert extraction_control_correct(genuine)


@pytest.mark.parametrize("name", ["obsolete", "invalid-type", "invalid-manager"])
def test_policy_negative_not_any_failure(name: str) -> None:
    from experiments.e017.oracle import policy_control_correct

    config = json.loads((HERE / "policies.json").read_bytes())[name]
    candidate = json.dumps(config).encode()
    unrelated = encode([{"msg": "unrelated runtime failure", "level": 50}])
    assert not policy_control_correct(name, candidate, unrelated, b"", 1)
    if name == "invalid-manager":
        expected = {
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
        expected = {
            "msg": "Config migration necessary",
            "level": 40,
            "oldConfig": config,
            "newConfig": (
                {"dependencyDashboard": {"enabled": True}}
                if name == "obsolete"
                else {"automerge": False}
            ),
        }
    raw = encode([expected])
    assert policy_control_correct(name, candidate, raw, b"", 1)
    assert not policy_control_correct(name, candidate, raw, b"", 0)
    assert not policy_control_correct(name, candidate, raw + unrelated, b"", 1)
