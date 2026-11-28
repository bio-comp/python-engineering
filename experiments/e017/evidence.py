"""Versioned local evidence identity and receipt admission.

A digest binds retained bytes, not an independent attestation of their origin.
The real report never admits the explicitly synthetic test condition.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from experiments.e017.oracle import CLOCK_SLOP, Receipt, State, digest, unique_json
from python_engineering.reporting.models import GIT_SHA, SHA256, Contract

RUNTIME_DISTRIBUTION = "npm-45.3.2-re2-fallback"
Q1_DISTRIBUTION_SHA = "a455fb623ca8e9e7f2a26d1e3a6e4f24683a1686bc56c19f27f7f70a218bdf09"
Q1_NPM_LOCK_SHA = "2fc2d0216896cd03911fe497a83cd432659fb5308a1691d89fbf674b33ae4222"
Q1_NODE_SHA = "d931c649850ffa7155b8ceffb400dc916ef325866e509cc52ae36e33e8fbb9a9"
Q1_UV_SHA = "b73acdf73b96c3ac9e56d2fa933427b3ee6a901e3cce6ba1e3ecb3f91ca0d86a"
Q1_PYTHON_SHA = "32b6777d62aba66726091c65e4a4631073a49b069e4267cc83d4a5df14009f91"
Q1_RENOVATE_SHA = "8596404ee41729a84b41a372a389ddcf515af2b83e0cffe95f10fc7307425e23"
Q1_VALIDATOR_SHA = "3bc1afcce7f0a8be6dd649df42e83ad55fc598ff422cdfd7847375cf66e9bfe4"
RunStage = Literal["extract", "lookup", "updates"]
Arm = Literal["renovate", "native-uv"]
Operation = Literal["policy", "initial-check", "update", "lock-check", "repeat"]


class EvidenceError(ValueError):
    """Evidence admission fails without producing a measured successful report."""

    def __init__(self, state: State, reason: str) -> None:
        self.state = state
        super().__init__(f"{state}: {reason}")


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise EvidenceError(State.FAIL, reason)


def read_bytes(path: Path) -> bytes:
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise EvidenceError(State.FAIL, "symlinked evidence path")
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise EvidenceError(State.BLOCKED, f"missing evidence: {path.name}") from exc


def read_model[T: Contract](path: Path, model: type[T]) -> T:
    raw = read_bytes(path)
    try:
        unique_json(raw)
        return model.model_validate_json(raw)
    except (ValueError, ValidationError) as exc:
        raise EvidenceError(State.FAIL, f"invalid evidence schema: {path.name}") from exc


def now() -> str:
    return datetime.now(UTC).isoformat()


def timestamp(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)", value):
        raise ValueError("timestamp must be an offset-aware ISO datetime")
    if datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError("timestamp requires offset")
    return value


def absolute(value: str) -> str:
    path = Path(value)
    if not path.is_absolute() or str(path) != value or ".." in path.parts:
        raise ValueError("expected canonical absolute path")
    return value


def nonzero_sha(value: str) -> str:
    if value == "0" * 64:
        raise ValueError("zero fingerprint")
    return value


class SourceIdentity(Contract):
    source_commit: GIT_SHA
    source_dirty: bool
    source_files: dict[str, SHA256] = Field(min_length=1)
    pyproject_sha256: SHA256
    lockfile_sha256: SHA256


class Executable(Contract):
    path: str
    sha256: SHA256
    version: str = Field(min_length=1)

    _absolute = field_validator("path")(absolute)
    _nonzero = field_validator("sha256")(nonzero_sha)


class RunIdentity(Contract):
    schema_version: Literal["e017-q1-r2-v3"] = "e017-q1-r2-v3"
    stage: RunStage
    source: SourceIdentity
    source_root: str
    execution_root: str
    prefix: str
    python: Executable
    python_entrypoint: str
    node: Executable
    uv: Executable
    renovate: Executable
    validator: Executable
    distribution: Literal["npm-45.3.2-re2-fallback", "synthetic-control"]
    distribution_sha256: SHA256
    npm_lock_sha256: SHA256
    fixture_sha256: dict[str, SHA256] = Field(min_length=1)
    executed_at: str
    platform: str = Field(min_length=1)

    _absolute = field_validator("source_root", "execution_root", "prefix", "python_entrypoint")(
        absolute
    )
    _nonzero = field_validator("distribution_sha256", "npm_lock_sha256")(nonzero_sha)
    _timestamp = field_validator("executed_at")(timestamp)

    @model_validator(mode="after")
    def condition(self) -> RunIdentity:
        if self.distribution == RUNTIME_DISTRIBUTION:
            if self.source.source_dirty:
                raise ValueError("real evidence requires clean source")
            if (
                self.distribution_sha256 != Q1_DISTRIBUTION_SHA
                or self.npm_lock_sha256 != Q1_NPM_LOCK_SHA
                or self.node.sha256 != Q1_NODE_SHA
                or self.uv.sha256 != Q1_UV_SHA
                or self.python.sha256 != Q1_PYTHON_SHA
                or self.renovate.sha256 != Q1_RENOVATE_SHA
                or self.validator.sha256 != Q1_VALIDATOR_SHA
            ):
                raise ValueError("not the established Q1 distribution/runtime condition")
        if (
            self.python.version != "3.14.10"
            or self.node.version != "v26.13.1"
            or not self.uv.version.startswith("uv 0.13.9 ")
            or self.renovate.version != "45.3.2"
            or self.validator.version != "45.3.2"
        ):
            raise ValueError("incorrect pinned runtime versions")
        dist = Path(self.prefix) / "node_modules/renovate/dist"
        if self.renovate.path != str(dist / "renovate.js") or self.validator.path != str(
            dist / "config-validator.js"
        ):
            raise ValueError("wrong distribution entrypoint")
        return self

    def fingerprint(self) -> str:
        return digest(self.model_dump_json().encode())

    def case_path(self, name: str) -> Path:
        return Path(self.execution_root) / name


class BoundExtraction(Receipt):
    started_at: str
    run_sha256: SHA256
    repetition: Literal[1, 2]
    cwd: str

    _timestamp = field_validator("started_at", "executed_at")(timestamp)
    _absolute = field_validator("cwd")(absolute)


class ProcessReceipt(Contract):
    started_at: str
    run_sha256: SHA256
    case_id: str = Field(min_length=1)
    repetition: Literal[1, 2, 3]
    arm: Arm
    operation: Operation
    fixture_sha256: SHA256
    command: tuple[str, ...] = Field(min_length=1)
    environment: dict[str, str] = Field(min_length=1)
    cwd: str
    executed_at: str
    returncode: int
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    stdout_sha256: SHA256
    stderr_sha256: SHA256

    _timestamp = field_validator("started_at", "executed_at")(timestamp)
    _absolute = field_validator("cwd")(absolute)


class ResolverReceipt(ProcessReceipt):
    before: dict[str, SHA256] = Field(min_length=1)
    after: dict[str, SHA256] = Field(min_length=1)


class PolicyReceipt(ProcessReceipt):
    expected_valid: bool
    config_sha256: SHA256
    control_correct: bool
    scope: Literal["schema validation only"]


def ordered(before: str, after: str, reason: str) -> None:
    """Compare same-host wall times, allowing only millisecond quantization."""
    require(datetime.fromisoformat(before) <= datetime.fromisoformat(after) + CLOCK_SLOP, reason)


def bind_timing(identity: RunIdentity, receipt: BoundExtraction | ProcessReceipt) -> None:
    ordered(identity.executed_at, receipt.started_at, "execution predates run start")
    ordered(receipt.started_at, receipt.executed_at, "execution completion predates start")


def nested_timing(parent: ProcessReceipt, child: ResolverReceipt) -> None:
    ordered(parent.started_at, child.started_at, "resolver starts before parent")
    ordered(child.executed_at, parent.executed_at, "resolver completes after parent")


def log_context(identity: RunIdentity, case: Path) -> str:
    # Exact pinned Renovate logger accepts LOG_CONTEXT as the emitted context.
    return digest(f"{identity.fingerprint()}:{case.name}".encode())


def expected_environment(
    identity: RunIdentity, case: Path, *, shim: bool = False
) -> dict[str, str]:
    home = case / "home"
    path = os.pathsep.join(
        (
            str(Path(identity.node.path).parent),
            str(Path(identity.uv.path).parent),
            str(Path(identity.python_entrypoint).parent),
            os.defpath,
        )
    )
    if shim:
        path = str(case / "bin") + os.pathsep + path
    return {
        "HOME": str(home),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "PATH": path,
        "LOG_FORMAT": "json",
        "LOG_LEVEL": "debug",
        **({"LOG_CONTEXT": log_context(identity, case)} if identity.stage != "updates" else {}),
        "RENOVATE_CACHE_DIR": str(case / "cache"),
        "RENOVATE_BASE_DIR": str(case / "base"),
        "RENOVATE_AUTODISCOVER": "false",
        "RENOVATE_ALLOW_SCRIPTS": "false",
        "RENOVATE_ALLOW_PLUGINS": "false",
        "RENOVATE_EXPOSE_ALL_ENV": "false",
        "RENOVATE_BINARY_SOURCE": "global",
        "UV_PYTHON_DOWNLOADS": "never",
    }


def bind_extraction(
    identity: RunIdentity,
    receipt: BoundExtraction,
    case_id: str,
    rep: int,
    fixture_sha: str,
) -> None:
    bind_timing(identity, receipt)
    case = identity.case_path(f"{case_id}-{identity.stage}-{rep}")
    require(
        identity.stage in ("extract", "lookup")
        and receipt.stage == identity.stage
        and receipt.case_id == case_id
        and receipt.repetition == rep
        and receipt.run_sha256 == identity.fingerprint()
        and receipt.fixture_sha256 == fixture_sha
        and receipt.distribution == identity.distribution
        and receipt.distribution_sha256 == identity.distribution_sha256
        and receipt.tool_version == identity.renovate.version
        and receipt.node_version == identity.node.version
        and receipt.python_version == identity.python.version
        and receipt.uv_version == identity.uv.version
        and receipt.cwd == str(case / "fixture")
        and receipt.command
        == (
            identity.node.path,
            identity.renovate.path,
            "--platform=local",
            f"--dry-run={identity.stage}",
        )
        and receipt.environment == expected_environment(identity, case),
        "extraction execution identity mismatch",
    )


def bind_process(
    identity: RunIdentity,
    receipt: ProcessReceipt,
    *,
    case_id: str,
    repetition: int,
    arm: Arm,
    operation: Operation,
    fixture_sha: str,
    command: tuple[str, ...],
    cwd: Path,
    env: dict[str, str],
    stdout: bytes,
    stderr: bytes,
) -> None:
    bind_timing(identity, receipt)
    require(
        receipt.run_sha256 == identity.fingerprint()
        and receipt.case_id == case_id
        and receipt.repetition == repetition
        and receipt.arm == arm
        and receipt.operation == operation
        and receipt.fixture_sha256 == fixture_sha
        and receipt.command == command
        and receipt.cwd == str(cwd)
        and receipt.environment == env
        and receipt.stdout_sha256 == digest(stdout)
        and receipt.stderr_sha256 == digest(stderr),
        f"process receipt mismatch: {case_id}/{arm}/{repetition}/{operation}",
    )
