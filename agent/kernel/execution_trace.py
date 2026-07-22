"""M4 Traceable Execution Model — convert RunResult → platform.execution.

Independent of legacy result_json projection so M6 Artifact lineage can reuse it.
"""

from __future__ import annotations

from typing import Any

from agent.kernel.types import Artifact, PolicyDecision, RunResult, ToolCallRecord


def to_execution_trace(
    result: RunResult,
    *,
    steps: list[Any] | None = None,
    incomplete: bool = False,
) -> dict[str, Any]:
    """Build ExecutionTrace document (ToolCall / PolicyDecision / ArtifactRef).

    Best-effort: includes whatever tool/policy/artifact records exist.
    Does not require a complete successful Skill run (cancel/timeout/fail OK).
    """
    step_by_tool = _index_steps_by_tool(steps or list(result.steps or []))

    tool_calls: list[dict[str, Any]] = []
    call_id_by_tool_seq: dict[tuple[str, int], str] = {}
    tool_seq_counter: dict[str, int] = {}

    for seq, tc in enumerate(result.tool_calls or [], start=1):
        call_id = f"tc_{seq}"
        tool_id = tc.tool_id
        tool_seq_counter[tool_id] = tool_seq_counter.get(tool_id, 0) + 1
        call_id_by_tool_seq[(tool_id, tool_seq_counter[tool_id])] = call_id
        step_no = _pop_step_no(step_by_tool, tool_id)
        tool_calls.append(_tool_call_dict(tc, call_id=call_id, seq=seq, step_no=step_no))

    # Reset counters for policy→call linking (nth occurrence of tool_id)
    tool_occ: dict[str, int] = {}
    policy_decisions: list[dict[str, Any]] = []
    for seq, pd in enumerate(result.policy_decisions or [], start=1):
        decision_id = f"pd_{seq}"
        call_id = None
        if pd.tool_id:
            tool_occ[pd.tool_id] = tool_occ.get(pd.tool_id, 0) + 1
            call_id = call_id_by_tool_seq.get((pd.tool_id, tool_occ[pd.tool_id]))
            # Fallback: last call with this tool_id
            if call_id is None:
                for tc_row in reversed(tool_calls):
                    if tc_row["tool_id"] == pd.tool_id:
                        call_id = tc_row["call_id"]
                        break
        step_no = None
        if call_id:
            for tc_row in tool_calls:
                if tc_row["call_id"] == call_id:
                    step_no = tc_row.get("step_no")
                    break
        if step_no is None and pd.tool_id:
            step_no = _peek_step_no(step_by_tool, pd.tool_id)
        policy_decisions.append(
            _policy_dict(pd, decision_id=decision_id, seq=seq, call_id=call_id, step_no=step_no)
        )

    artifacts: list[dict[str, Any]] = []
    type_counts: dict[str, int] = {}
    for art in result.artifacts or []:
        type_counts[art.type] = type_counts.get(art.type, 0) + 1
        artifacts.append(_artifact_ref(art, n=type_counts[art.type]))

    deny_count = sum(1 for d in policy_decisions if not d.get("ok"))
    summary: dict[str, Any] = {
        "tool_count": len(tool_calls),
        "policy_decision_count": len(policy_decisions),
        "policy_deny_count": deny_count,
        "artifact_count": len(artifacts),
        "artifact_types": [a["type"] for a in artifacts],
        "incomplete": bool(incomplete) or not result.success,
    }

    return {
        "schema_version": 1,
        "tool_calls": tool_calls,
        "policy_decisions": policy_decisions,
        "artifacts": artifacts,
        "summary": summary,
    }


def merge_execution_into_result_json(
    result_json: dict[str, Any],
    execution: dict[str, Any],
    *,
    skill_id: str | None = None,
    skill_version: str | None = None,
) -> dict[str, Any]:
    """Attach execution under platform without dropping legacy keys."""
    data = dict(result_json or {})
    platform = dict(data.get("platform") or {})
    if skill_id:
        platform["skill_id"] = skill_id
    if skill_version:
        platform["skill_version"] = skill_version
    platform["execution"] = execution
    # Keep Foundation id lists for older UI
    if "tool_ids" not in platform:
        platform["tool_ids"] = [t["tool_id"] for t in execution.get("tool_calls") or []]
    if "policy_ids" not in platform:
        platform["policy_ids"] = sorted(
            {d["policy_id"] for d in execution.get("policy_decisions") or []}
        )
    if "artifact_types" not in platform:
        platform["artifact_types"] = list(
            (execution.get("summary") or {}).get("artifact_types") or []
        )
    data["platform"] = platform
    return data


def _tool_call_dict(
    tc: ToolCallRecord, *, call_id: str, seq: int, step_no: int | None
) -> dict[str, Any]:
    return {
        "call_id": call_id,
        "seq": seq,
        "tool_id": tc.tool_id,
        "status": tc.status,
        "latency_ms": tc.latency_ms,
        "input_summary": tc.input_summary,
        "output_summary": tc.output_summary,
        "error_message": tc.error_message,
        "step_no": step_no,
    }


def _policy_dict(
    pd: PolicyDecision,
    *,
    decision_id: str,
    seq: int,
    call_id: str | None,
    step_no: int | None,
) -> dict[str, Any]:
    return {
        "decision_id": decision_id,
        "seq": seq,
        "policy_id": pd.policy_id,
        "ok": bool(pd.ok),
        "reason": pd.reason,
        "tool_id": pd.tool_id,
        "call_id": call_id,
        "step_no": step_no,
    }


def _artifact_ref(art: Artifact, *, n: int) -> dict[str, Any]:
    artifact_id = art.id or f"art_{art.type}_{n}"
    ref: dict[str, Any] = {"type": art.type}
    if art.type == "summary":
        ref["field"] = "summary"
    elif art.type == "sql":
        ref["field"] = "sql"
    elif art.type == "table":
        ref["field"] = "table_preview"
    elif art.type == "chart":
        ref["field"] = "charts"
        # Prefer chart payload id for content resolution; artifact_id is platform UUID
        if isinstance(art.payload, dict) and art.payload.get("id"):
            ref["chart_id"] = art.payload.get("id")
    elif art.type == "report":
        ref["field"] = "report"
    return {"artifact_id": artifact_id, "type": art.type, "ref": ref}


def _index_steps_by_tool(steps: list[Any]) -> dict[str, list[int]]:
    """Map tool_id → queue of step_no (1-based order of appearance)."""
    out: dict[str, list[int]] = {}
    for i, step in enumerate(steps, start=1):
        step_no = getattr(step, "step_no", None)
        if step_no is None:
            step_no = i
        tool_id = None
        output = getattr(step, "output_json", None) or {}
        if isinstance(output, dict):
            tool_id = output.get("tool_id")
        node = getattr(step, "node_name", None)
        # Fallback map common nodes
        if not tool_id and node:
            tool_id = {
                "generate_sql": "sql.generate",
                "validate_sql": "sql.validate_policy",
                "execute_sql": "sql.execute_select",
                "build_charts": "chart.build_spec",
                "write_report": "report.build",
            }.get(str(node))
        if tool_id:
            out.setdefault(str(tool_id), []).append(int(step_no))
    return out


def _pop_step_no(index: dict[str, list[int]], tool_id: str) -> int | None:
    q = index.get(tool_id) or []
    if not q:
        return None
    return q.pop(0)


def _peek_step_no(index: dict[str, list[int]], tool_id: str) -> int | None:
    q = index.get(tool_id) or []
    return q[0] if q else None
