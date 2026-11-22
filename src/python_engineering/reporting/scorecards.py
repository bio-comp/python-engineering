"""Non-prescriptive category requirements; thresholds belong to frozen run protocols."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryProfile:
    category_id: str
    display: str
    required_questions: tuple[str, ...]
    gate_examples: tuple[str, ...]


CATEGORY_PROFILES: tuple[CategoryProfile, ...] = (
    CategoryProfile(
        "static_typing",
        "Static analysis and typing",
        (
            "Unique true defects beyond Ruff/mypy baseline",
            "Known-bad sensitivity and known-good false positives",
            "Diagnostic quality / remediation cost",
            "Exact Python and Pydantic support",
            "Cold/warm execution overhead",
        ),
        ("Incorrectly rejects supported syntax", "Critical semantic false fix"),
    ),
    CategoryProfile(
        "hook_orchestration",
        "Git hooks, pre-push and CI",
        (
            "Staged-only file fidelity, including unstaged/deleted paths",
            "Checker command equivalence between candidates",
            "Nonzero failure propagation and no-match behavior",
            "Cold/warm setup and full-check placement cost",
        ),
        ("Failed check returns success", "Lost mandatory CI gate"),
    ),
    CategoryProfile(
        "workflow_orchestration",
        "Durable workflow orchestration",
        (
            "Idempotency and duplicate side effects",
            "Retries, timeout, persistence and crash recovery",
            "Delivery semantics under failure injection",
            "Deployment dependencies and operational burden",
        ),
        ("Lost acknowledged task", "Uncontrolled duplicate external effect"),
    ),
    CategoryProfile(
        "dependency_compatibility",
        "Wheel/dependency compatibility",
        (
            "Supported wheel tags and exact target platform/ABI",
            "Unknown/source-only artifact policy and false assurances",
            "Incremental coverage over uv/pip baseline",
            "Lockfile consistency and target-environment scope",
        ),
        ("False green for required deployment target",),
    ),
    CategoryProfile(
        "performance_diagnostics",
        "Profiling and trace tooling",
        (
            "Trace quality for chosen failure investigation",
            "Correctness-preserving instrumentation",
            "Overhead on representative workloads",
            "Async/concurrency trace limitations",
        ),
        ("Changes functional result",),
    ),
    CategoryProfile(
        "citation_verification",
        "Reference and claim verification",
        (
            "Reference existence",
            "Bibliographic metadata correctness",
            "Retraction/correction/publication status",
            "Document or source identity",
            "Independent source-to-claim support (distinct from metadata)",
        ),
        ("False claim of verified scientific support",),
    ),
    CategoryProfile(
        "coding_agent_retrieval",
        "Coding-agent retrieval and assistance",
        (
            "Independently oracle-verified task success",
            "Unsupported claims / API-hallucination rate",
            "Retrieval source exact-version accuracy",
            "Agent iterations, latency, token spend, and regressions",
        ),
        ("Unverified tool permissions", "Regression on required correctness task"),
    ),
)
