"""Capture verifiable local environment facts; absent agent telemetry stays absent."""

import hashlib
import importlib.metadata
import platform
import subprocess
from pathlib import Path

from pydantic import BaseModel

from python_engineering.e010.contracts import (
    RetrievalBudget,
    RetrievalCondition,
    RunManifest,
    TaskSpec,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, stderr=subprocess.PIPE
    ).strip()


def capture_unrun_manifest(
    *,
    task: TaskSpec,
    condition: RetrievalCondition,
    budget: RetrievalBudget,
    project_root: Path,
    seed: int,
) -> RunManifest:
    """Record local facts; no agent or external-tool access is asserted."""
    current_python = platform.python_version()
    if current_python != task.python_version:
        raise ValueError("active Python version differs from frozen task requirement")
    packages = {
        "python-engineering-lab": importlib.metadata.version("python-engineering-lab"),
        "pydantic": importlib.metadata.version("pydantic"),
    }
    # The standard library is versioned with CPython; distributions are resolved
    # by their exact declared distribution identity, never a similar import name.
    installed_version = (
        current_python
        if task.package == "python-stdlib"
        else importlib.metadata.version(task.package)
    )
    if installed_version != task.exact_version:
        raise ValueError("installed package version differs from frozen task requirement")
    if task.package != "python-stdlib":
        packages[task.package] = installed_version
    return RunManifest(
        task_id=task.task_id,
        condition=condition,
        retrieval_budget=budget,
        model_id=None,
        model_settings_sha256=None,
        agent_config_sha256=None,
        python_version=current_python,
        package_versions=packages,
        os_platform=platform.platform(),
        git_sha=_git(project_root, "rev-parse", "HEAD"),
        fixture_sha256=task.fixture_sha256,
        seed=seed,
        workspace_dirty=bool(_git(project_root, "status", "--porcelain=v1")),
        declared_target_tools=tuple(sorted(condition.target_tools)),
        observed_target_tools=None,
        declared_non_target_tools=("filesystem", "python", "ordinary_documentation"),
        observed_non_target_tools=None,
        isolation_receipt_id=None,
        agent_tool_events_available=False,
        tokens_available=False,
        wall_time_available=False,
        money_available=False,
    )


def write_new_record(path: Path, record: BaseModel) -> str:
    """Create a record exclusively and return its byte digest for external anchoring.

    Exclusive creation is NOT post-write filesystem immutability.
    """
    payload = (record.model_dump_json(indent=2) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(payload)
    return hashlib.sha256(payload).hexdigest()
