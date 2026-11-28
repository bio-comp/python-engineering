"""Deterministic controls for independently expected manifest/lock transitions."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from experiments.e017.updates import (
    Artifact,
    ArtifactError,
    ComponentResult,
    Spec,
    component_result,
    invocation_evidence,
    update_errors,
)

SPEC = Spec(
    case_id="unit",
    dependency="idna",
    old_version="3.9",
    new_version="3.10",
    classification="independent",
)
BEFORE_MANIFEST = b'[project]\ndependencies=["idna==3.9"]\n'
AFTER_MANIFEST = b'[project]\ndependencies=["idna==3.10"]\n'
BEFORE_LOCK = b'[[package]]\nname="idna"\nversion="3.9"\n'
AFTER_LOCK = b'[[package]]\nname="idna"\nversion="3.10"\n'
BEFORE = {"pyproject.toml": BEFORE_MANIFEST, "uv.lock": BEFORE_LOCK, "sentinel.txt": b"keep"}
AFTER = {"pyproject.toml": AFTER_MANIFEST, "uv.lock": AFTER_LOCK, "sentinel.txt": b"keep"}
GOOD = ComponentResult(
    msg="E017 component result",
    level=30,
    manifest=AFTER_MANIFEST.decode(),
    repeatedManifest=AFTER_MANIFEST.decode(),
    artifacts=(Artifact(file="uv.lock", error=None, contentsPresent=True),),
)


def test_positive_update() -> None:
    assert (
        update_errors(
            SPEC,
            BEFORE,
            AFTER_MANIFEST,
            AFTER,
            artifact=GOOD,
            arm="renovate",
            returncode=0,
            lock_check_exit=0,
            repeated=AFTER,
        )
        == ()
    )
    assert (
        update_errors(
            SPEC,
            BEFORE,
            AFTER_MANIFEST,
            AFTER,
            artifact=None,
            arm="native-uv",
            returncode=0,
            lock_check_exit=0,
            repeated=AFTER,
        )
        == ()
    )


@pytest.mark.parametrize(
    "variant",
    [
        "wrong-target",
        "unchanged",
        "unrelated",
        "missing-lock",
        "wrong-lock",
        "extra-file",
        "malformed-lock",
        "duplicate-lock",
    ],
)
def test_update_bytes_negative(variant: str) -> None:
    actual = AFTER.copy()
    if variant == "wrong-target":
        actual["pyproject.toml"] = b"idna==9.9"
    elif variant == "unchanged":
        actual["pyproject.toml"] = BEFORE_MANIFEST
    elif variant == "unrelated":
        actual["sentinel.txt"] = b"changed"
    elif variant == "missing-lock":
        del actual["uv.lock"]
    elif variant == "wrong-lock":
        actual["uv.lock"] = BEFORE_LOCK
    elif variant == "extra-file":
        actual["unexpected"] = b"x"
    elif variant == "malformed-lock":
        actual["uv.lock"] = b"[["
    else:
        actual["uv.lock"] = AFTER_LOCK + AFTER_LOCK
    assert update_errors(
        SPEC,
        BEFORE,
        AFTER_MANIFEST,
        actual,
        artifact=GOOD,
        arm="renovate",
        returncode=0,
        lock_check_exit=0,
        repeated=actual,
    )


@pytest.mark.parametrize(
    "variant",
    [
        "missing-artifact",
        "artifact-error",
        "duplicate-artifact",
        "wrong-file",
        "repeat-change",
        "nonzero",
        "missing-check",
        "failed-check",
        "missing-repeat",
        "changed-repeat",
    ],
)
def test_update_evidence_negative(variant: str) -> None:
    artifact: ComponentResult | None = GOOD
    exit_code = 0
    check_exit: int | None = 0
    repeated: dict[str, bytes] | None = AFTER
    if variant == "missing-artifact":
        artifact = None
    elif variant == "artifact-error":
        artifact = GOOD.model_copy(
            update={
                "artifacts": (
                    Artifact(
                        file=None,
                        error=ArtifactError(fileName="uv.lock", stderr="No solution found"),
                        contentsPresent=False,
                    ),
                )
            }
        )
    elif variant == "duplicate-artifact":
        artifact = GOOD.model_copy(update={"artifacts": GOOD.artifacts * 2})
    elif variant == "wrong-file":
        artifact = GOOD.model_copy(
            update={"artifacts": (Artifact(file="other", error=None, contentsPresent=True),)}
        )
    elif variant == "repeat-change":
        artifact = GOOD.model_copy(update={"repeatedManifest": BEFORE_MANIFEST.decode()})
    elif variant == "nonzero":
        exit_code = 1
    elif variant == "missing-check":
        check_exit = None
    elif variant == "failed-check":
        check_exit = 1
    elif variant == "missing-repeat":
        repeated = None
    else:
        repeated = BEFORE
    assert update_errors(
        SPEC,
        BEFORE,
        AFTER_MANIFEST,
        AFTER,
        artifact=artifact,
        arm="renovate",
        returncode=exit_code,
        lock_check_exit=check_exit,
        repeated=repeated,
    )


def test_component_wire_protocol() -> None:
    raw = GOOD.model_dump_json().encode() + b"\n"
    assert component_result(raw) == GOOD
    for bad in (raw + raw, raw[:-1], b"not json\n", b'{"msg":"error","level":50}\n' + raw):
        with pytest.raises(ValueError):
            component_result(bad)


def test_uv_invocation_receipt(tmp_path: Path) -> None:
    p = tmp_path / "uv.jsonl"
    assert not invocation_evidence(p, "idna", False)
    p.write_text(
        '["lock","--check"]\n["lock","--upgrade-package","idna"]\n["lock","--check"]\n["lock"]\n'
    )
    assert invocation_evidence(p, "idna", False)
    assert not invocation_evidence(p, "requests", False)
    assert not invocation_evidence(p, "idna", True)
    p.write_text('["lock","--check"]\n["lock","--check"]\n["lock"]\n')
    assert not invocation_evidence(p, "idna", False)


@given(st.binary().filter(lambda b: b != b"keep"))
def test_arbitrary_unrelated_mutation_is_rejected(data: bytes) -> None:
    actual = {**AFTER, "sentinel.txt": data}
    assert update_errors(
        SPEC,
        BEFORE,
        AFTER_MANIFEST,
        actual,
        artifact=GOOD,
        arm="renovate",
        returncode=0,
        lock_check_exit=0,
        repeated=actual,
    )
