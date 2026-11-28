"""Independent E-017 expectations and fail-closed log adjudication."""

from __future__ import annotations

import json
import re
from collections import Counter
from enum import StrEnum
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from python_engineering.reporting.models import SHA256, Contract


class State(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


Stage = Literal["extract", "lookup"]


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant: {value}")


def unique_json(data: bytes) -> None:
    """Reject ambiguous JSON before typed validation."""
    json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)


def safe_relative(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or path.as_posix() != name
        or name == "."
        or ".git" in path.parts
    )


class Expected(Contract):
    manager: str = Field(min_length=1)
    file: str = Field(min_length=1)
    name: str = Field(min_length=1)
    datasource: str | None
    value: str | None
    digest: str | None = None
    dep_type: str | None = None
    locked: str | None = None
    package: str | None = None
    required_skip: str | None = None

    def signature(self) -> tuple[str | None, ...]:
        return (
            self.manager,
            self.file,
            self.name,
            self.package or self.name,
            self.datasource,
            self.value,
            self.digest,
            self.dep_type,
            self.locked,
        )


class Fixture(Contract):
    case_id: str = Field(pattern=r"^[a-z0-9-]+$")
    files: dict[str, str] = Field(min_length=1)
    expected: tuple[Expected, ...] = Field(min_length=1)
    excluded: tuple[str, ...]
    notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def check_paths(self) -> Fixture:
        if not all(safe_relative(name) for name in self.files):
            raise ValueError("unsafe fixture path")
        signatures = [entry.signature() for entry in self.expected]
        if len(set(signatures)) != len(signatures):
            raise ValueError("duplicate expectation")
        if any(item.file not in self.files for item in self.expected):
            raise ValueError("expected declaration file absent")
        if set(self.excluded) & {item.name for item in self.expected}:
            raise ValueError("contradictory exclusion")
        return self

    def fingerprint(self) -> str:
        return digest(self.model_dump_json().encode())


def load_fixtures(path: Path) -> tuple[Fixture, ...]:
    raw = path.read_bytes()
    unique_json(raw)
    fixtures = TypeAdapter(tuple[Fixture, ...]).validate_json(raw)
    if not fixtures or len({case.case_id for case in fixtures}) != len(fixtures):
        raise ValueError("empty or duplicate corpus")
    return fixtures


class Raw(BaseModel):
    # Renovate records include version-specific ancillary metadata. Only
    # explicit projected fields are used; the complete raw bytes are retained.
    model_config = ConfigDict(strict=True, extra="ignore")


class Log(Raw):
    msg: str
    level: int


class Update(Raw):
    newVersion: str | None = Field(default=None, min_length=1)
    newValue: str | None = None
    newDigest: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def target_required(self) -> Update:
        if self.newVersion is None and self.newDigest is None:
            raise ValueError("missing update version or digest")
        return self


class RawDependency(Raw):
    depName: str = Field(min_length=1)
    packageName: str = Field(min_length=1)
    datasource: str | None = None
    currentValue: str | None = None
    currentDigest: str | None = None
    depType: str | None = None
    lockedVersion: str | None = None
    skipReason: str | None = None
    warnings: list[dict[str, str]] | None = None
    updates: list[Update] | None = None
    currentVersion: str | None = None
    registryUrl: str | None = None


class PackageFile(Raw):
    packageFile: str
    deps: list[RawDependency]


class ExtractPayload(Raw):
    packageFiles: dict[str, list[PackageFile]]


class LookupPayload(Raw):
    config: dict[str, list[PackageFile]]


class Count(Raw):
    fileCount: int = Field(ge=0)
    depCount: int = Field(ge=0)


class Stats(Raw):
    managers: dict[str, Count]
    total: Count


class ExtractionSummary(Raw):
    stats: Stats


class Observed(Contract):
    identity: Expected
    skip_reason: str | None
    lookup_warnings: tuple[str, ...] | None
    updates: tuple[Update, ...] | None
    current_version: str | None
    registry_url: str | None


class Counts(Contract):
    category: str
    expected: int = Field(ge=0)
    observed: int = Field(ge=0)
    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    fn: int = Field(ge=0)
    skipped: int = Field(ge=0)


class Receipt(Contract):
    case_id: str
    stage: Stage
    fixture_sha256: SHA256
    distribution: Literal["npm-45.3.2-re2-fallback", "synthetic-control"]
    tool_version: Literal["45.3.2"]
    distribution_sha256: SHA256
    node_version: str = Field(min_length=1)
    python_version: str = Field(min_length=1)
    uv_version: str = Field(min_length=1)
    command: tuple[str, ...] = Field(min_length=1)
    environment: dict[str, str] = Field(min_length=1)
    executed_at: str = Field(min_length=1)
    returncode: int
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    stdout_sha256: SHA256
    stderr_sha256: SHA256
    before: dict[str, SHA256] = Field(min_length=1)
    after: dict[str, SHA256]


class Verdict(Contract):
    case_id: str
    stage: Stage
    state: State
    diagnostics: tuple[str, ...]
    counts: tuple[Counts, ...] = ()
    records: tuple[Observed, ...] = ()


def _records(files: dict[str, list[PackageFile]]) -> tuple[Observed, ...]:
    records: list[Observed] = []
    seen_files: set[tuple[str, str]] = set()
    for manager, entries in files.items():
        for entry in entries:
            key = manager, entry.packageFile
            if key in seen_files or not safe_relative(entry.packageFile):
                raise ValueError("duplicate or unsafe package file")
            seen_files.add(key)
            for dep in entry.deps:
                records.append(
                    Observed(
                        identity=Expected(
                            manager=manager,
                            file=entry.packageFile,
                            name=dep.depName,
                            package=dep.packageName,
                            datasource=dep.datasource,
                            value=dep.currentValue,
                            digest=dep.currentDigest,
                            dep_type=dep.depType,
                            locked=dep.lockedVersion,
                        ),
                        skip_reason=dep.skipReason,
                        lookup_warnings=None
                        if dep.warnings is None
                        else tuple(warning.get("message", "") for warning in dep.warnings),
                        updates=None if dep.updates is None else tuple(dep.updates),
                        current_version=dep.currentVersion,
                        registry_url=dep.registryUrl,
                    )
                )
    return tuple(records)


def _parse(stdout: bytes, stage: Stage) -> tuple[tuple[Observed, ...], tuple[str, ...]]:
    if not stdout.endswith(b"\n"):
        raise ValueError("unterminated log stream")
    events: list[tuple[Log, bytes]] = []
    for line in stdout.splitlines():
        unique_json(line)
        events.append((Log.model_validate_json(line), line))
    names = [event.msg for event, _ in events]
    result_name = "Extracted dependencies" if stage == "extract" else "packageFiles with updates"
    required = ("Dependency extraction complete", result_name, "Repository finished")
    if any(names.count(name) != 1 for name in required):
        raise ValueError("missing or duplicate run records")
    positions = [names.index(name) for name in required]
    if positions != sorted(positions):
        raise ValueError("invalid run record ordering")
    summary = ExtractionSummary.model_validate_json(events[positions[0]][1]).stats
    payload = events[positions[1]][1]
    files = (
        ExtractPayload.model_validate_json(payload).packageFiles
        if stage == "extract"
        else LookupPayload.model_validate_json(payload).config
    )
    records = _records(files)
    actual_counts = {
        manager: (len(entries), sum(len(entry.deps) for entry in entries))
        for manager, entries in files.items()
    }
    expected_counts = {
        manager: (count.fileCount, count.depCount) for manager, count in summary.managers.items()
    }
    if actual_counts != expected_counts or (
        summary.total.fileCount != sum(count[0] for count in actual_counts.values())
        or summary.total.depCount != len(records)
    ):
        raise ValueError("summary and payload counts disagree")
    problems: list[str] = []
    for event, _ in events:
        msg = event.msg
        if event.level >= 40 and msg not in {
            "RE2 not usable, falling back to RegExp",
            "GitHub token is required for some dependencies",
        }:
            problems.append("warning/error: " + msg)
        elif re.search(
            r"failed to (?:parse|look up)|error parsing|datasource unknown error|artifacterror",
            msg,
            re.I,
        ):
            problems.append("diagnostic: " + msg)
    return records, tuple(problems)


def judge_logs(
    case: Fixture,
    stage: Stage,
    receipt: Receipt | None,
    stdout: bytes,
    stderr: bytes,
) -> Verdict:
    def result(state: State, *reasons: str) -> Verdict:
        return Verdict(case_id=case.case_id, stage=stage, state=state, diagnostics=reasons)

    if receipt is None:
        return result(State.BLOCKED, "missing execution receipt")
    if (
        receipt.case_id != case.case_id
        or receipt.stage != stage
        or receipt.fixture_sha256 != case.fingerprint()
        or receipt.stdout_sha256 != digest(stdout)
        or receipt.stderr_sha256 != digest(stderr)
    ):
        return result(State.FAIL, "receipt does not bind observation")
    required_before = {name: digest(content.encode()) for name, content in case.files.items()}
    if receipt.before != required_before or receipt.after != required_before:
        return result(State.FAIL, "fixture bytes changed or missing")
    if receipt.returncode or stderr:
        return result(State.FAIL, "nonzero exit or unexpected stderr")
    try:
        records, diagnostic_errors = _parse(stdout, stage)
    except (ValueError, ValidationError) as exc:
        return result(State.FAIL, "invalid log protocol: " + str(exc))
    expected = Counter(item.signature() for item in case.expected)
    actual = Counter(item.identity.signature() for item in records)
    errors = list(diagnostic_errors)
    if not records:
        errors.append("empty inventory")
    if any(count > 1 for count in actual.values()):
        errors.append("duplicate dependency records")
    if expected != actual:
        errors.append("missing or unexpected dependency identities")
    if any(item.identity.name in case.excluded for item in records):
        errors.append("excluded dependency extracted")
    matched = {item.identity.signature(): item for item in records}
    for item in case.expected:
        found = matched.get(item.signature())
        if found is None:
            continue
        if item.required_skip and found.skip_reason != item.required_skip:
            errors.append("expected skip missing: " + item.name)
        elif (
            not item.required_skip
            and found.skip_reason
            and (stage == "lookup" or found.skip_reason != "github-token-required")
        ):
            errors.append("critical dependency skipped: " + item.name)
        if (
            stage == "lookup"
            and not item.required_skip
            and (
                found.lookup_warnings != ()
                or found.updates is None
                or not found.current_version
                or not found.registry_url
            )
        ):
            errors.append("missing/failed critical lookup: " + item.name)
    counts = []
    for category in sorted(
        {item.manager for item in case.expected} | {item.identity.manager for item in records}
    ):
        e = Counter({k: n for k, n in expected.items() if k[0] == category})
        a = Counter({k: n for k, n in actual.items() if k[0] == category})
        counts.append(
            Counts(
                category=category,
                expected=e.total(),
                observed=a.total(),
                tp=(e & a).total(),
                fp=(a - e).total(),
                fn=(e - a).total(),
                skipped=sum(
                    item.identity.manager == category and item.skip_reason is not None
                    for item in records
                ),
            )
        )
    return Verdict(
        case_id=case.case_id,
        stage=stage,
        state=State.FAIL if errors else State.PASS,
        diagnostics=tuple(errors),
        counts=tuple(counts),
        records=records,
    )


def extraction_control_correct(verdict: Verdict) -> bool:
    """Require the seeded malformed input to fail for the observed parse error."""
    if verdict.stage != "extract":
        return False
    if verdict.case_id != "malformed-toml":
        return verdict.state == State.PASS
    return (
        verdict.state == State.FAIL
        and not verdict.records
        and "diagnostic: Failed to parse and validate pyproject file" in verdict.diagnostics
        and "empty inventory" in verdict.diagnostics
        and "missing or unexpected dependency identities" in verdict.diagnostics
    )


def policy_control_correct(
    name: str,
    candidate: bytes,
    stdout: bytes,
    stderr: bytes,
    returncode: int,
) -> bool:
    """An unrelated failure is not a successful negative control."""
    if stderr or not stdout.endswith(b"\n"):
        return False
    try:
        unique_json(candidate)
        config = json.loads(candidate)
        events = []
        for line in stdout.splitlines():
            unique_json(line)
            events.append((Log.model_validate_json(line), json.loads(line)))
    except ValueError, ValidationError:
        return False
    successes = sum(
        event.msg == "Config validated successfully against 1 file(s)" for event, _ in events
    )
    significant = [
        (event, raw)
        for event, raw in events
        if event.level >= 40
        and event.msg
        != "RE2 not usable, falling back to RegExp: regex validation may be inaccurate"
    ]
    if name in {"repository", "administrative"}:
        return returncode == 0 and successes == 1 and not significant
    if returncode != 1 or successes:
        return False
    if name in {"obsolete", "invalid-type"}:
        expected = (
            {"dependencyDashboard": {"enabled": True}}
            if name == "obsolete"
            else {"automerge": False}
        )
        migrations = [
            raw for event, raw in significant if event.msg == "Config migration necessary"
        ]
        return (
            len(migrations) == 1
            and migrations[0].get("oldConfig") == config
            and migrations[0].get("newConfig") == expected
            and all(
                event.msg == "Config migration necessary"
                or event.msg.startswith("Config migration diff:")
                for event, _ in significant
            )
        )
    if name == "invalid-manager":
        if len(significant) != 1:
            return False
        event, raw = significant[0]
        errors = raw.get("errors")
        return (
            event.msg == "Found errors in configuration"
            and isinstance(errors, list)
            and len(errors) == 1
            and isinstance(errors[0], dict)
            and errors[0].get("topic") == "Configuration Error"
            and isinstance(errors[0].get("message"), str)
            and errors[0]["message"].startswith("Invalid enabledManagers:")
            and "not-a-manager" in errors[0]["message"]
        )
    return False
