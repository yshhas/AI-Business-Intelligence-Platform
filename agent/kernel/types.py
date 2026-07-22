"""Kernel contract types — Enterprise Data Agent Platform (M1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import UUID


@dataclass
class Artifact:
    type: str  # summary | sql | table | chart | report
    payload: dict[str, Any]
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type, "payload": self.payload}
        if self.id:
            out["id"] = self.id
        return out


@dataclass
class ToolCallRecord:
    tool_id: str
    status: str  # ok | error | degraded
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    error_message: str | None = None
    latency_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "status": self.status,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "error_message": self.error_message,
            "latency_ms": self.latency_ms,
        }


@dataclass
class PolicyDecision:
    policy_id: str
    ok: bool
    reason: str | None = None
    tool_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "ok": self.ok,
            "reason": self.reason,
            "tool_id": self.tool_id,
        }


@dataclass
class RunRequest:
    skill_id: str
    workspace_id: UUID
    input: dict[str, Any]
    policy_context: dict[str, Any] = field(default_factory=dict)
    runtime_hints: dict[str, Any] = field(default_factory=dict)
    # Injected by product shell — not serialized
    execute_select: Callable[[str, int], dict[str, Any]] | None = None
    schema: list[dict[str, Any]] = field(default_factory=list)
    duckdb_table: str = ""
    # P1.1 cooperative abort — Worker callback; raises RunAborted
    cancel_check: Callable[[], None] | None = None


@dataclass
class RunResult:
    success: bool
    skill_id: str
    artifacts: list[Artifact] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    policy_decisions: list[PolicyDecision] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    error_message: str | None = None
    # Skill-private bridge for Facade → AnalysisOutcome.steps
    steps: list[Any] = field(default_factory=list)
    # T-09 Skill Lifecycle lite — version pinned for this Run
    skill_version: str | None = None

    def artifact_types(self) -> list[str]:
        return [a.type for a in self.artifacts]

    def to_legacy_result_json(self, *, mock: bool = False) -> dict[str, Any]:
        """Project Artifacts to ChatBI-era result_json (backward compatible)."""
        summary = ""
        sql: str | None = None
        table = {"columns": [], "rows": []}
        charts: list[dict[str, Any]] = []
        report: dict[str, Any] | None = None

        for art in self.artifacts:
            if art.type == "summary":
                summary = str(art.payload.get("text") or "")
            elif art.type == "sql":
                sql = art.payload.get("sql")
            elif art.type == "table":
                table = {
                    "columns": art.payload.get("columns") or [],
                    "rows": art.payload.get("rows") or [],
                }
            elif art.type == "chart":
                charts.append(dict(art.payload))
            elif art.type == "report" and art.payload:
                report = dict(art.payload)

        platform: dict[str, Any] = {
            "skill_id": self.skill_id,
            "artifact_types": self.artifact_types(),
            "tool_ids": [t.tool_id for t in self.tool_calls],
            "policy_ids": sorted({p.policy_id for p in self.policy_decisions}),
        }
        if self.skill_version:
            platform["skill_version"] = self.skill_version

        return {
            "summary": summary,
            "sql": sql,
            "table_preview": table,
            "charts": charts,
            "report": report,
            "limitations": list(self.limitations),
            "mock": mock,
            # Optional platform perception (non-breaking)
            "platform": platform,
        }
