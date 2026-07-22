"""Run lifecycle helpers — failure classes and status constants (M2 + M4 trace columns)."""

from __future__ import annotations

from typing import Any

TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled", "timed_out"})
ACTIVE_STATUSES = frozenset({"pending", "running"})

FAILURE_ENQUEUE = "enqueue_error"
FAILURE_CAPACITY = "capacity_rejected"
FAILURE_BUDGET = "budget_rejected"
FAILURE_POLICY = "policy_denied"
FAILURE_CONNECTOR = "connector_error"
FAILURE_SKILL = "skill_error"
FAILURE_TIMEOUT = "timeout"
FAILURE_CANCELLED = "cancelled"
FAILURE_RUNTIME_RECLAIMED = "runtime_reclaimed"
FAILURE_INTERNAL = "internal_error"
FAILURE_UNKNOWN = "unknown"

TIMEOUT_LIMITATIONS = [
    "Run timed out (wall-clock budget). New Skill checkpoints stop after the signal; "
    "in-flight LLM HTTP or SQL queries may still finish but success/memory writes are fenced.",
]

CANCEL_LIMITATIONS = [
    "Run cancelled. New Skill checkpoints stop after the signal; "
    "in-flight LLM HTTP or SQL queries may still finish but success/memory writes are fenced.",
]


def classify_exception(exc: BaseException) -> str:
    msg = str(exc).lower()
    if "sql policy rejected" in msg or "sql gate rejected" in msg:
        return FAILURE_POLICY
    if "forbidden keyword" in msg or "not in allowlist" in msg:
        return FAILURE_POLICY
    if msg.startswith("connector error:") or "connector error:" in msg:
        return FAILURE_CONNECTOR
    return FAILURE_SKILL


def attach_run_platform(
    result_json: dict | None,
    *,
    status: str,
    failure_class: str | None,
    cancel_requested: bool,
    timeout_seconds: int | None,
    task_id: str,
) -> dict:
    data = dict(result_json or {})
    platform = dict(data.get("platform") or {})
    platform["run"] = {
        "run_id": task_id,
        "status": status,
        "failure_class": failure_class,
        "cancel_requested": cancel_requested,
        "timeout_seconds": timeout_seconds,
    }
    if status in {"cancelled", "timed_out"}:
        execution = dict(platform.get("execution") or {})
        if execution:
            summary = dict(execution.get("summary") or {})
            summary["incomplete"] = True
            execution["summary"] = summary
            platform["execution"] = execution
    if failure_class == FAILURE_RUNTIME_RECLAIMED:
        execution = dict(platform.get("execution") or {})
        summary = dict(execution.get("summary") or {})
        summary["incomplete"] = True
        execution["summary"] = summary
        platform["execution"] = execution
    data["platform"] = platform
    return data


def apply_trace_columns(task: Any, result_json: dict | None) -> None:
    """Denormalize M4 filter columns from platform.execution / data_plane onto task."""
    platform = dict((result_json or {}).get("platform") or {})
    skill = platform.get("skill_id")
    if isinstance(skill, str) and skill:
        task.skill_id = skill[:64]
    version = platform.get("skill_version")
    if isinstance(version, str) and version:
        task.skill_version = version[:32]
    plane = platform.get("data_plane") or {}
    source = plane.get("source_type") if isinstance(plane, dict) else None
    if isinstance(source, str) and source:
        task.source_type = source[:20]
    execution = platform.get("execution") or {}
    summary = execution.get("summary") if isinstance(execution, dict) else None
    deny_count = 0
    if isinstance(summary, dict):
        deny_count = int(summary.get("policy_deny_count") or 0)
    decisions = execution.get("policy_decisions") if isinstance(execution, dict) else None
    if isinstance(decisions, list) and deny_count == 0:
        deny_count = sum(1 for d in decisions if isinstance(d, dict) and not d.get("ok"))
    task.policy_denied = deny_count > 0
