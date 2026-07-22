"""Skill data.bi — wraps existing LangGraph ChatBI pipeline (no second orchestrator)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from agent.contracts import validate_charts
from agent.graph import build_graph
from agent.kernel.tools import tool_execute_select
from agent.kernel.types import (
    Artifact,
    PolicyDecision,
    RunRequest,
    RunResult,
    ToolCallRecord,
)
from agent.state import AnalysisContext, StepRecord

# Map graph node names → tool_ids (trace without rewriting every node)
_NODE_TO_TOOL = {
    "generate_sql": "sql.generate",
    "validate_sql": "sql.validate_policy",
    "execute_sql": "sql.execute_select",
    "build_charts": "chart.build_spec",
    "write_report": "report.build",
}


def run_data_bi_skill(request: RunRequest) -> RunResult:
    if request.execute_select is None:
        return RunResult(
            success=False,
            skill_id="data.bi",
            error_message="execute_select callback required for data.bi",
        )

    tool_calls: list[ToolCallRecord] = []
    policy_decisions: list[PolicyDecision] = []
    steps: list[StepRecord] = []

    allowed = set(request.policy_context.get("allowed_tables") or [])
    if request.duckdb_table:
        allowed.add(request.duckdb_table)
    default_limit = int(request.policy_context.get("default_limit") or 200)
    max_retries = int(request.policy_context.get("max_retries") or 2)
    hints = request.runtime_hints or {}
    inp = request.input or {}

    inner = request.execute_select
    hitl_plan_only = bool(hints.get("hitl_plan_only"))

    def execute_select(sql: str, limit: int) -> dict[str, Any]:
        if hitl_plan_only:
            raise RuntimeError(
                "HITL plan mode: Data Plane execute is forbidden until approve (H2)"
            )
        if request.cancel_check is not None:
            request.cancel_check()
        return tool_execute_select(
            sql,
            limit,
            allowed_tables=allowed,
            default_limit=default_limit,
            inner_execute=inner,
            tool_calls=tool_calls,
            policy_decisions=policy_decisions,
        )

    ctx = AnalysisContext(
        workspace_id=request.workspace_id,
        dataset_id=UUID(str(inp.get("dataset_id"))),
        question=str(inp.get("question") or ""),
        duckdb_table=request.duckdb_table,
        schema=list(request.schema or []),
        default_limit=default_limit,
        max_retries=max_retries,
        execute_select=execute_select,
        llm_api_key=str(hints.get("llm_api_key") or ""),
        llm_base_url=str(hints.get("llm_base_url") or ""),
        llm_model=str(hints.get("llm_model") or ""),
        allow_heuristic_sql=bool(hints.get("allow_heuristic_sql", True)),
        allowed_tables=sorted(allowed),
        source_type=str(inp.get("source_type") or hints.get("source_type") or "file"),
        schema_link_max_columns=int(hints.get("schema_link_max_columns") or 12),
        schema_synonyms=(
            hints.get("schema_synonyms")
            if isinstance(hints.get("schema_synonyms"), dict)
            else None
        ),
        llm_max_retries=(
            int(hints["llm_max_retries"]) if hints.get("llm_max_retries") is not None else None
        ),
        llm_retry_backoff_seconds=(
            float(hints["llm_retry_backoff_seconds"])
            if hints.get("llm_retry_backoff_seconds") is not None
            else None
        ),
        llm_retry_backoff_max_seconds=(
            float(hints["llm_retry_backoff_max_seconds"])
            if hints.get("llm_retry_backoff_max_seconds") is not None
            else None
        ),
        cancel_check=request.cancel_check,
        hitl_plan_only=hitl_plan_only,
    )

    def sink(step: StepRecord) -> None:
        # Enrich step for Demo / agent_run_steps without a new audit system
        out = dict(step.output_json or {})
        tool_id = _NODE_TO_TOOL.get(step.node_name)
        if tool_id:
            out.setdefault("tool_id", tool_id)
        if step.node_name == "validate_sql":
            out.setdefault("policy_id", "sql.select_gate")
        if step.node_name == "load_context":
            out.setdefault("skill_id", "data.bi")
        step.output_json = out
        steps.append(step)

        # Derive tool_calls from nodes (execute also recorded in tool_execute_select)
        if tool_id and tool_id != "sql.execute_select":
            tool_calls.append(
                ToolCallRecord(
                    tool_id=tool_id,
                    status=step.status if step.status in ("ok", "error", "degraded") else "ok",
                    input_summary=_brief(step.input_json),
                    output_summary=_brief(step.output_json),
                    error_message=step.error_message,
                    latency_ms=step.latency_ms,
                )
            )
        if step.node_name == "validate_sql":
            ok = step.status == "ok"
            policy_decisions.append(
                PolicyDecision(
                    policy_id="sql.select_gate",
                    ok=ok,
                    reason=None if ok else step.error_message,
                    tool_id="sql.validate_policy",
                )
            )

    if request.cancel_check is not None:
        request.cancel_check()
    graph = build_graph(ctx, sink=sink)
    final: dict[str, Any] = graph.invoke({})

    if final.get("status") == "succeeded" and final.get("sql_final"):
        artifacts, limitations = _artifacts_from_final(final)
        return RunResult(
            success=True,
            skill_id="data.bi",
            artifacts=artifacts,
            tool_calls=tool_calls,
            policy_decisions=policy_decisions,
            limitations=limitations,
            steps=steps,
        )

    err = final.get("error") or final.get("gate_error") or "Analysis failed"
    if not any(s.node_name == "fail" or s.status == "error" for s in steps):
        steps.append(StepRecord(node_name="fail", status="error", error_message=err))
    return RunResult(
        success=False,
        skill_id="data.bi",
        artifacts=[],
        tool_calls=tool_calls,
        policy_decisions=policy_decisions,
        limitations=["Analysis failed before producing a trusted result."],
        error_message=err,
        steps=steps,
    )


def _artifacts_from_final(final: dict[str, Any]) -> tuple[list[Artifact], list[str]]:
    preview = final.get("preview") or {"columns": [], "rows": [], "row_count": 0}
    charts_raw = final.get("charts") or []
    charts, chart_lims = validate_charts(
        list(charts_raw) if isinstance(charts_raw, list) else []
    )
    limitations = list(final.get("limitations") or [])
    limitations.extend(chart_lims)

    artifacts: list[Artifact] = [
        Artifact(
            type="summary",
            id=str(uuid4()),
            payload={"text": final.get("summary") or ""},
        ),
        Artifact(
            type="sql",
            id=str(uuid4()),
            payload={"sql": final.get("sql_final")},
        ),
        Artifact(
            type="table",
            id=str(uuid4()),
            payload={
                "columns": preview.get("columns") or [],
                "rows": preview.get("rows") or [],
            },
        ),
    ]
    for i, ch in enumerate(charts):
        artifacts.append(
            Artifact(
                type="chart",
                id=str(uuid4()),
                payload=dict(ch) if isinstance(ch, dict) else ch,
            )
        )
    report = final.get("report")
    if isinstance(report, dict) and report:
        artifacts.append(
            Artifact(type="report", id=str(uuid4()), payload=report)
        )
    return artifacts, limitations


def _brief(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return None
    # Keep step payloads small in tool_calls
    keys = list(data.keys())[:8]
    return {k: data[k] for k in keys}
