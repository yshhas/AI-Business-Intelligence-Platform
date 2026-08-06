"""Public agent entrypoint — Facade over Enterprise Data Agent Kernel.

Workers should import `run_analysis` (compatible) or `agent.kernel.runtime.run`.
Do not import graph/nodes/skills internals from backend.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from agent.guardrails import apply_output_guardrails
from agent.kernel import runtime as kernel_runtime
from agent.kernel.execution_trace import merge_execution_into_result_json, to_execution_trace
from agent.kernel.types import RunRequest
from agent.state import AnalysisContext, AnalysisOutcome, StepRecord

logger = logging.getLogger(__name__)


def _sql_quality_from_steps(steps: list[StepRecord]) -> dict[str, Any] | None:
    """Project link_schema step → platform.sql_quality (audit only)."""
    for step in reversed(steps or []):
        if getattr(step, "node_name", None) != "link_schema":
            continue
        out = getattr(step, "output_json", None) or {}
        if not isinstance(out, dict):
            return None
        return {
            "schema_version": 1,
            "link_status": out.get("link_status"),
            "link_method": out.get("link_method"),
            "link_reason": out.get("link_reason"),
            "selected_tables": list(out.get("selected_tables") or []),
            "selected_columns": list(out.get("selected_columns") or []),
            "column_count_full": out.get("column_count_full"),
            "column_count_linked": out.get("column_count_linked"),
        }
    return None


def _outcome_from_result(result: Any) -> AnalysisOutcome:
    steps: list[StepRecord] = list(result.steps or [])
    legacy = result.to_legacy_result_json(mock=False)
    execution = to_execution_trace(result, steps=steps, incomplete=not result.success)
    legacy = merge_execution_into_result_json(
        legacy,
        execution,
        skill_id=result.skill_id,
        skill_version=result.skill_version,
    )
    sql_quality = _sql_quality_from_steps(steps)
    if sql_quality:
        platform = dict(legacy.get("platform") or {})
        platform["sql_quality"] = sql_quality
        legacy["platform"] = platform
    legacy = apply_output_guardrails(legacy)
    return AnalysisOutcome(
        success=result.success,
        result_json=legacy,
        steps=steps,
        error_message=result.error_message,
    )


def context_to_run_request(ctx: AnalysisContext) -> RunRequest:
    allowed = list(ctx.allowed_tables) if ctx.allowed_tables else [ctx.duckdb_table]
    if ctx.duckdb_table and ctx.duckdb_table not in allowed:
        allowed.append(ctx.duckdb_table)
    skill_id = (ctx.skill_id or "data.bi").strip() or "data.bi"
    return RunRequest(
        skill_id=skill_id,
        workspace_id=ctx.workspace_id,
        input={
            "question": ctx.question,
            "dataset_id": str(ctx.dataset_id),
            "source_type": ctx.source_type,
        },
        policy_context={
            "allowed_tables": allowed,
            "default_limit": ctx.default_limit,
            "max_retries": ctx.max_retries,
        },
        runtime_hints={
            "llm_api_key": ctx.llm_api_key,
            "llm_base_url": ctx.llm_base_url,
            "llm_model": ctx.llm_model,
            "allow_heuristic_sql": ctx.allow_heuristic_sql,
            "source_type": ctx.source_type,
            "schema_link_max_columns": ctx.schema_link_max_columns,
            "schema_synonyms": ctx.schema_synonyms,
            "llm_max_retries": ctx.llm_max_retries,
            "llm_retry_backoff_seconds": ctx.llm_retry_backoff_seconds,
            "llm_retry_backoff_max_seconds": ctx.llm_retry_backoff_max_seconds,
            "hitl_plan_only": bool(ctx.hitl_plan_only),
            "hitl_execute_only": bool(ctx.hitl_execute_only),
            "approved_sql": ctx.approved_sql,
        },
        execute_select=ctx.execute_select,
        schema=list(ctx.schema or []),
        duckdb_table=ctx.duckdb_table,
        cancel_check=ctx.cancel_check,
    )


def run_analysis(ctx: AnalysisContext) -> AnalysisOutcome:
    """Compatibility Facade: AnalysisContext → kernel.run(skill_id from ctx)."""
    skill_id = (ctx.skill_id or "data.bi").strip() or "data.bi"
    has_llm = bool(ctx.llm_api_key)
    logger.info(
        "Analysis started skill_id=%s ws=%s source=%s has_llm=%s",
        skill_id, str(ctx.workspace_id), ctx.source_type, has_llm,
    )
    request = context_to_run_request(ctx)
    result = kernel_runtime.run(request)
    outcome = _outcome_from_result(result)
    if outcome.success:
        logger.info(
            "Analysis completed success=True steps=%d has_repair=%s",
            len(outcome.steps), bool(outcome.result_json.get("repair_history")),
        )
    else:
        err = (outcome.error_message or "")[:200]
        logger.warning("Analysis failed error=%s", err)
    return outcome


def run_skill(
    *,
    skill_id: str,
    workspace_id: UUID,
    question: str,
    dataset_id: UUID,
    duckdb_table: str,
    schema: list[dict[str, Any]],
    execute_select: Any,
    default_limit: int = 200,
    max_retries: int = 2,
    llm_api_key: str = "",
    llm_base_url: str = "",
    llm_model: str = "",
    allow_heuristic_sql: bool = True,
    allowed_tables: list[str] | None = None,
    source_type: str = "file",
    schema_synonyms: dict[str, list[str]] | None = None,
) -> AnalysisOutcome:
    """Thin helper for callers that already speak skill_id (any registered Skill)."""
    ctx = AnalysisContext(
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        question=question,
        duckdb_table=duckdb_table,
        schema=schema,
        default_limit=default_limit,
        max_retries=max_retries,
        execute_select=execute_select,
        skill_id=skill_id,
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        allow_heuristic_sql=allow_heuristic_sql,
        allowed_tables=allowed_tables,
        source_type=source_type,
        schema_synonyms=schema_synonyms,
    )
    return run_analysis(ctx)
