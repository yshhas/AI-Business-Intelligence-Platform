"""LangGraph node functions for slim Text-to-SQL pipeline."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from agent.gates.sql_gate import validate_and_normalize_sql
from agent.llm import LLMError, chat_completion_result
from agent.prompts_sql import PROMPT_SQL_VERSION, build_text_to_sql_prompts
from agent.repair_classify import (
    RepairHint,
    classify_repair_error,
    classify_with_hint,
)
from agent.run_control import checkpoint
from agent.schema_linking import filter_schema_by_columns, link_schema as run_link_schema
from agent.schemas_llm import parse_sql_draft
from agent.state import AnalysisContext, AnalysisState, StepRecord

logger = logging.getLogger(__name__)

StepSink = Callable[[StepRecord], None]


def _emit(sink: StepSink | None, record: StepRecord) -> None:
    if sink is not None:
        sink(record)


def load_context(state: AnalysisState, *, ctx: AnalysisContext, sink: StepSink | None) -> AnalysisState:
    checkpoint(ctx)
    t0 = time.perf_counter()
    out = {
        "question": ctx.question,
        "workspace_id": str(ctx.workspace_id),
        "dataset_id": str(ctx.dataset_id),
        "duckdb_table": ctx.duckdb_table,
        "schema": ctx.schema,
        "retry_count": 0,
        "max_retries": ctx.max_retries,
        "default_limit": ctx.default_limit,
        "status": "running",
        "limitations": [],
        "hitl_plan_only": bool(ctx.hitl_plan_only),
        "hitl_execute_only": bool(ctx.hitl_execute_only),
    }
    if ctx.hitl_execute_only:
        approved = (ctx.approved_sql or "").strip()
        if not approved:
            logger.warning("HITL execute-only missing approved SQL")
            _emit(
                sink,
                StepRecord(
                    node_name="load_context",
                    status="error",
                    input_json={"hitl_execute_only": True},
                    error_message="HITL execute-only: approved SQL snapshot missing",
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                ),
            )
            return {
                **state,
                **out,
                "status": "failed",
                "error": "HITL execute-only: approved SQL snapshot missing",
                "gate_error": "HITL execute-only: approved SQL snapshot missing",
                "link_status": "failed",
                "link_reason": "hitl_approved_sql_missing",
            }
        out["sql_draft"] = approved
        out["sql_final"] = approved
        logger.info("HITL execute-only mode activated")
        lims = list(out.get("limitations") or [])
        note = "HITL: execute-only — using approved SQL snapshot (no regenerate)."
        if note not in lims:
            lims.append(note)
        out["limitations"] = lims
    _emit(
        sink,
        StepRecord(
            node_name="load_context",
            status="ok",
            input_json={"question": ctx.question, "dataset_id": str(ctx.dataset_id)},
            output_json={
                "duckdb_table": ctx.duckdb_table,
                "column_count": len(ctx.schema),
                "hitl_execute_only": bool(ctx.hitl_execute_only),
            },
            latency_ms=int((time.perf_counter() - t0) * 1000),
        ),
    )
    return {**state, **out}


def link_schema(state: AnalysisState, *, ctx: AnalysisContext, sink: StepSink | None) -> AnalysisState:
    """E1-A: deterministic schema linking — always emits an observable step."""
    checkpoint(ctx)
    t0 = time.perf_counter()
    table = state.get("duckdb_table") or ctx.duckdb_table
    schema = state.get("schema") or ctx.schema
    question = state.get("question") or ctx.question
    allowed = list(ctx.allowed_tables or [])
    if table and table not in allowed:
        allowed = [table, *allowed]

    result = run_link_schema(
        question=question,
        schema=list(schema or []),
        table=table,
        allowed_tables=allowed,
        max_columns=int(ctx.schema_link_max_columns or 12),
        synonyms=ctx.schema_synonyms,
    )
    step_status = "error" if result.link_status == "failed" else "ok"
    err = None
    if result.link_status == "failed":
        err = f"schema linking failed: {result.link_reason or 'unusable schema'}"
        logger.warning(
            "Schema linking failed reason=%s", result.link_reason or "unusable",
        )
    elif result.link_status == "partial":
        logger.info(
            "Schema linking partial linked=%d/%d method=%s",
            result.column_count_linked, result.column_count_full, result.link_method,
        )
    else:
        logger.info(
            "Schema linking ok linked=%d/%d method=%s",
            result.column_count_linked, result.column_count_full, result.link_method,
        )

    _emit(
        sink,
        StepRecord(
            node_name="link_schema",
            status=step_status,
            input_json={
                "question": question,
                "table": table,
                "column_count_full": result.column_count_full,
                "max_columns": int(ctx.schema_link_max_columns or 12),
            },
            output_json=result.as_step_output(),
            error_message=err,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        ),
    )

    patch: dict[str, Any] = {
        "selected_tables": result.selected_tables,
        "selected_columns": result.selected_columns,
        "link_status": result.link_status,
        "link_method": result.link_method,
        "link_reason": result.link_reason,
        "column_count_full": result.column_count_full,
        "column_count_linked": result.column_count_linked,
    }
    if err:
        patch["error"] = err
        patch["status"] = "failed"
    return {**state, **patch}


def generate_sql(state: AnalysisState, *, ctx: AnalysisContext, sink: StepSink | None) -> AnalysisState:
    checkpoint(ctx)
    if ctx.hitl_execute_only or state.get("hitl_execute_only"):
        msg = "HITL execute-only: SQL regeneration is forbidden"
        _emit(
            sink,
            StepRecord(
                node_name="generate_sql",
                status="error",
                error_message=msg,
                latency_ms=0,
            ),
        )
        return {
            **state,
            "status": "failed",
            "error": msg,
            "gate_error": msg,
            "sql_draft": "",
        }
    t0 = time.perf_counter()
    table = state.get("duckdb_table") or ctx.duckdb_table
    full_schema = state.get("schema") or ctx.schema
    question = state.get("question") or ctx.question
    gate_error = state.get("gate_error") or ""
    link_status = state.get("link_status")
    selected_columns = list(state.get("selected_columns") or [])
    if selected_columns:
        schema = filter_schema_by_columns(list(full_schema or []), selected_columns)
    else:
        schema = list(full_schema or [])

    llm_meta: dict[str, Any] | None = None
    try:
        sql, llm_meta = _produce_sql(
            ctx,
            table=table,
            schema=schema,
            question=question,
            gate_error=gate_error,
            link_status=link_status,
            repair_hint=state.get("repair_hint"),
        )
        status = "ok"
        err = None
    except Exception as exc:  # noqa: BLE001
        sql = ""
        status = "error"
        err = str(exc)
        logger.warning("SQL generation failed error=%s", err[:200])

    output: dict[str, Any] = {"prompt_sql_version": PROMPT_SQL_VERSION}
    if sql:
        output["sql_draft"] = sql
    if llm_meta:
        output["llm"] = llm_meta
    if link_status:
        output["link_status"] = link_status
    if selected_columns:
        output["selected_columns"] = selected_columns
    _emit(
        sink,
        StepRecord(
            node_name="generate_sql",
            status=status,
            input_json={
                "question": question,
                "gate_error": gate_error or None,
                "link_status": link_status,
                "selected_columns": selected_columns or None,
                "prompt_sql_version": PROMPT_SQL_VERSION,
            },
            output_json=output or None,
            error_message=err,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        ),
    )
    if err:
        return {**state, "error": err, "status": "failed", "sql_draft": ""}
    mode = "llm" if ctx.llm_api_key else "heuristic"
    logger.info(
        "SQL generated mode=%s has_repair_hint=%s",
        mode, bool(state.get("repair_hint")),
    )
    return {**state, "sql_draft": sql, "gate_error": ""}


def validate_sql(state: AnalysisState, *, ctx: AnalysisContext, sink: StepSink | None) -> AnalysisState:
    checkpoint(ctx)
    t0 = time.perf_counter()
    draft = state.get("sql_draft") or ""
    table = state.get("duckdb_table") or ctx.duckdb_table
    allowed = set(ctx.allowed_tables or [])
    if table:
        allowed.add(table)
    if not allowed:
        allowed = {table} if table else set()
    gate = validate_and_normalize_sql(
        draft,
        allowed_tables=allowed,
        default_limit=int(state.get("default_limit") or ctx.default_limit),
    )
    repair_class = None if gate.ok else classify_repair_error(gate.error, stage="validate")
    out_json: dict[str, Any] = {}
    if gate.ok and gate.sql:
        out_json["sql_final"] = gate.sql
    else:
        out_json["repair_class"] = repair_class
        out_json["repair_stage"] = "validate"
    _emit(
        sink,
        StepRecord(
            node_name="validate_sql",
            status="ok" if gate.ok else "error",
            input_json={"sql_draft": draft},
            output_json=out_json or None,
            error_message=None if gate.ok else gate.error,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        ),
    )
    if gate.ok and gate.sql:
        history = list(state.get("repair_history") or [])
        if int(state.get("retry_count") or 0) > 0:
            history.append({
                "attempt": int(state.get("retry_count") or 0),
                "sql_draft": draft,
                "sql_final": gate.sql,
                "gate_passed": True,
                "stage": "validate_ok",
            })
        return {
            **state,
            "gate_ok": True,
            "gate_error": "",
            "sql_final": gate.sql,
            "repair_history": history,
        }
    retry = int(state.get("retry_count") or 0) + 1
    err = gate.error or "SQL Gate rejected query"
    tagged = f"[{repair_class}] {err}" if repair_class else err
    hint = classify_with_hint(err, stage="validate")
    if not hint.is_repairable:
        logger.error(
            "SQL Gate reject non-repairable repair_class=%s retry=%d",
            hint.repair_class, retry,
        )
    else:
        logger.warning(
            "SQL Gate reject repair_class=%s is_repairable=True retry=%d",
            hint.repair_class, retry,
        )
    history = list(state.get("repair_history") or [])
    history.append({
        "attempt": retry,
        "sql_draft": draft,
        "error": err,
        "repair_class": repair_class,
        "is_repairable": hint.is_repairable,
        "gate_passed": False,
        "stage": "validate_fail",
    })
    return {
        **state,
        "gate_ok": False,
        "gate_error": tagged,
        "repair_class": repair_class,
        "repair_stage": "validate",
        "repair_hint": (
            {
                "repair_class": hint.repair_class,
                "action": hint.action,
                "is_repairable": hint.is_repairable,
            }
            if not gate.ok
            else None
        ),
        "retry_count": retry,
        "sql_final": "",
        "repair_history": history,
    }


def execute_sql(state: AnalysisState, *, ctx: AnalysisContext, sink: StepSink | None) -> AnalysisState:
    checkpoint(ctx)
    t0 = time.perf_counter()
    sql = state.get("sql_final") or ""
    limit = int(state.get("default_limit") or ctx.default_limit)
    try:
        # execute_select MUST enforce Gate again inside duckdb_service.run_select
        preview = ctx.execute_select(sql, limit)
        _emit(
            sink,
            StepRecord(
                node_name="execute_sql",
                status="ok",
                input_json={"sql": sql},
                output_json={
                    "row_count": preview.get("row_count"),
                    "columns": preview.get("columns"),
                },
                latency_ms=int((time.perf_counter() - t0) * 1000),
            ),
        )
        # Record execute success in repair_history when retry happened
        history = list(state.get("repair_history") or [])
        if int(state.get("retry_count") or 0) > 0:
            history.append({
                "attempt": int(state.get("retry_count") or 0),
                "sql_final": sql,
                "gate_passed": True,
                "stage": "execute_ok",
            })
        return {**state, "preview": preview, "error": "", "repair_history": history}
    except Exception as exc:  # noqa: BLE001
        retry = int(state.get("retry_count") or 0) + 1
        msg = str(exc)
        repair_class = classify_repair_error(msg, stage="execute")
        tagged = f"[{repair_class}] {msg}"
        logger.warning(
            "SQL execution failed repair_class=%s retry=%d",
            repair_class, retry,
        )
        hint = classify_with_hint(msg, stage="execute")
        history = list(state.get("repair_history") or [])
        history.append({
            "attempt": retry,
            "sql_draft": sql,
            "error": msg,
            "repair_class": repair_class,
            "is_repairable": hint.is_repairable,
            "gate_passed": False,
            "stage": "execute_fail",
        })
        _emit(
            sink,
            StepRecord(
                node_name="execute_sql",
                status="error",
                input_json={"sql": sql},
                output_json={"repair_class": repair_class, "repair_stage": "execute"},
                error_message=msg,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            ),
        )
        return {
            **state,
            "error": msg,
            "retry_count": retry,
            "gate_error": tagged,
            "repair_class": repair_class,
            "repair_stage": "execute",
            "repair_hint": {
                "repair_class": hint.repair_class,
                "action": hint.action,
                "is_repairable": hint.is_repairable,
            },
            "repair_history": history,
        }


def summarize(state: AnalysisState, *, ctx: AnalysisContext, sink: StepSink | None) -> AnalysisState:
    checkpoint(ctx)
    t0 = time.perf_counter()
    preview = state.get("preview") or {}
    sql = state.get("sql_final") or ""
    question = state.get("question") or ctx.question
    rows = preview.get("rows") or []
    cols = preview.get("columns") or []

    summary, llm_meta = _produce_summary(
        ctx, question=question, sql=sql, columns=cols, rows=rows
    )
    mode = "llm" if (llm_meta and llm_meta.get("status") == "ok") else "heuristic"
    logger.info(
        "Summary generated mode=%s row_count=%d",
        mode, len(rows),
    )
    limitations = list(state.get("limitations") or [])
    for item in (
        "Single-dataset DuckDB analysis only.",
        "SQL must pass deterministic SQL Gate before execution.",
    ):
        if item not in limitations:
            limitations.append(item)
    out_json: dict[str, Any] = {"summary": summary}
    if llm_meta:
        out_json["llm"] = llm_meta
    # P4: expose repair_history for Eval observability
    repair_history = state.get("repair_history")
    if repair_history:
        out_json["repair_history"] = repair_history
    retry_count = state.get("retry_count")
    if retry_count is not None:
        out_json["retry_count"] = retry_count
    _emit(
        sink,
        StepRecord(
            node_name="summarize",
            status="ok",
            input_json={"row_count": preview.get("row_count"), "sql": sql},
            output_json=out_json,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        ),
    )
    return {
        **state,
        "summary": summary,
        "limitations": limitations,
        "charts": [],
        "report": None,
        # Main SQL path succeeded; charts/report may still degrade later.
        "status": "succeeded",
    }


def build_charts(state: AnalysisState, *, ctx: AnalysisContext, sink: StepSink | None) -> AnalysisState:
    """Heuristic ChartSpec only — never asks LLM for executable chart structure."""
    checkpoint(ctx)
    from agent.charts import build_charts_from_preview, enhance_chart_copy
    from agent.contracts import validate_charts

    t0 = time.perf_counter()
    preview = state.get("preview") or {}
    question = state.get("question") or ctx.question
    summary = state.get("summary") or ""
    limitations = list(state.get("limitations") or [])

    try:
        charts, lims = build_charts_from_preview(question=question, preview=preview)
        limitations.extend(lims)

        chart_llm_calls: list[dict[str, Any]] = []

        def _llm_copy(**kwargs: Any) -> tuple[str, str]:
            title, rationale, meta = _llm_chart_copy(ctx, **kwargs)
            if meta:
                chart_llm_calls.append(meta)
            return title, rationale

        if ctx.llm_api_key and charts:
            charts = enhance_chart_copy(
                charts,
                question=question,
                summary=summary,
                llm_fn=_llm_copy,
            )

        kept, vlims = validate_charts(list(charts))
        limitations.extend(vlims)
        status = "ok"
        err = None
        chart_out: dict[str, Any] = {
            "chart_count": len(kept),
            "types": [c.get("type") for c in kept],
        }
        if chart_llm_calls:
            chart_out["llm"] = _merge_llm_metas(chart_llm_calls)
    except Exception as exc:  # noqa: BLE001 — enhancement layer
        kept = []
        status = "degraded"
        err = str(exc)
        limitations.append(f"build_charts degraded: {err}")
        chart_out = {"chart_count": 0, "types": []}
        logger.warning("Chart generation degraded error=%s", err[:150])

    if status == "ok":
        logger.info(
            "Charts built chart_count=%d types=%s",
            len(kept), [c.get("type") for c in kept],
        )

    _emit(
        sink,
        StepRecord(
            node_name="build_charts",
            status=status,
            input_json={"row_count": preview.get("row_count")},
            output_json=chart_out,
            error_message=err,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        ),
    )
    return {**state, "charts": kept, "limitations": limitations, "status": "succeeded"}


def write_report(state: AnalysisState, *, ctx: AnalysisContext, sink: StepSink | None) -> AnalysisState:
    checkpoint(ctx)
    from agent.report import build_report

    t0 = time.perf_counter()
    preview = state.get("preview") or {}
    question = state.get("question") or ctx.question
    summary = state.get("summary") or ""
    sql = state.get("sql_final") or ""
    charts = list(state.get("charts") or [])
    limitations = list(state.get("limitations") or [])

    try:
        report_llm_meta: dict[str, Any] | None = None

        def _llm_report(**kwargs: Any) -> str:
            nonlocal report_llm_meta
            text, meta = _llm_report_markdown(ctx, **kwargs)
            report_llm_meta = meta
            return text

        report = build_report(
            question=question,
            summary=summary,
            sql=sql,
            preview=preview,
            charts=charts,
            limitations=limitations,
            llm_fn=_llm_report if ctx.llm_api_key else None,
        )
        status = "ok"
        err = None
        report_out: dict[str, Any] = {
            "title": report.get("title"),
            "has_markdown": bool(report.get("markdown")),
        }
        if report_llm_meta:
            report_out["llm"] = report_llm_meta
    except Exception as exc:  # noqa: BLE001
        report = {
            "title": "分析简报",
            "markdown": f"## 结论\n\n{summary or '（报告生成失败，仅保留摘要）'}",
            "sections": [{"heading": "结论", "body": summary or ""}],
        }
        status = "degraded"
        err = str(exc)
        limitations.append(f"write_report degraded: {err}")
        report_out = {
            "title": report.get("title"),
            "has_markdown": bool(report.get("markdown")),
        }
        logger.warning("Report generation degraded error=%s", err[:150])

    if status == "ok":
        logger.info(
            "Report generated has_markdown=%s chart_count=%d",
            bool(report.get("markdown")), len(charts),
        )

    _emit(
        sink,
        StepRecord(
            node_name="write_report",
            status=status,
            input_json={"chart_count": len(charts)},
            output_json=report_out,
            error_message=err,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        ),
    )
    return {
        **state,
        "report": report,
        "limitations": limitations,
        "status": "succeeded",
    }


def _merge_llm_metas(metas: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate multiple LLM calls in one step (e.g. chart title rewrites)."""
    if not metas:
        return {}
    if len(metas) == 1:
        return dict(metas[0])
    prompt = 0
    completion = 0
    total = 0
    latency = 0
    attempts = 0
    has_usage = False
    for m in metas:
        latency += int(m.get("latency_ms") or 0)
        attempts += int(m.get("attempts") or 1)
        usage = m.get("usage")
        if isinstance(usage, dict):
            has_usage = True
            prompt += int(usage.get("prompt_tokens") or 0)
            completion += int(usage.get("completion_tokens") or 0)
            total += int(usage.get("total_tokens") or 0)
    out: dict[str, Any] = {
        "model": metas[0].get("model"),
        "latency_ms": latency,
        "attempts": attempts,
        "status": "ok",
        "call_count": len(metas),
    }
    if has_usage:
        out["usage"] = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }
    return out


def _produce_sql(
    ctx: AnalysisContext,
    *,
    table: str,
    schema: list[dict[str, Any]],
    question: str,
    gate_error: str,
    link_status: str | None = None,
    repair_hint: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    if ctx.llm_api_key:
        allowed = list(ctx.allowed_tables or [table])
        dialect = "PostgreSQL" if (ctx.source_type == "postgres_ro" or "." in table) else "DuckDB"
        system, user = build_text_to_sql_prompts(
            dialect=dialect,
            table=table,
            allowed_tables=allowed,
            schema=schema,
            question=question,
            gate_error=gate_error,
            link_status=link_status,
            repair_hint=repair_hint,
        )
        result = chat_completion_result(
            api_key=ctx.llm_api_key,
            base_url=ctx.llm_base_url,
            model=ctx.llm_model,
            system=system,
            user=user,
            response_format={"type": "json_object"},
            max_retries=ctx.llm_max_retries,
            retry_backoff_seconds=ctx.llm_retry_backoff_seconds,
            retry_backoff_max_seconds=ctx.llm_retry_backoff_max_seconds,
        )
        return parse_sql_draft(result.content), result.as_step_llm()

    if not ctx.allow_heuristic_sql:
        raise LLMError("LLM_API_KEY empty and ALLOW_HEURISTIC_SQL is false")

    return (
        _heuristic_sql(table=table, schema=schema, question=question),
        {"status": "skipped", "mode": "heuristic"},
    )


def _quote_relation(table: str) -> str:
    """Quote bare DuckDB names or schema-qualified Postgres relations."""
    if "." in table:
        schema, name = table.split(".", 1)
        return f'"{schema}"."{name}"'
    return f'"{table}"'


def _heuristic_sql(*, table: str, schema: list[dict[str, Any]], question: str) -> str:
    cols = [str(c.get("name")) for c in schema if isinstance(c, dict) and c.get("name")]
    q = question.lower()
    rel = _quote_relation(table)
    dim = next((c for c in cols if c.lower() in {"region", "area", "category", "product", "name"}), None)
    metric = next(
        (c for c in cols if c.lower() in {"amount", "sales", "revenue", "qty", "quantity", "total", "value"}),
        None,
    )
    if dim and metric and any(k in q for k in ("汇总", "合计", "sum", "rank", "排序", "按", "group")):
        return (
            f'SELECT "{dim}" AS dim, SUM("{metric}") AS total '
            f"FROM {rel} GROUP BY \"{dim}\" ORDER BY total DESC"
        )
    col_list = ", ".join(f'"{c}"' for c in cols[:12]) or "*"
    return f"SELECT {col_list} FROM {rel}"


def _produce_summary(
    ctx: AnalysisContext,
    *,
    question: str,
    sql: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None]:
    preview_txt = str(rows[:5])
    if ctx.llm_api_key:
        try:
            result = chat_completion_result(
                api_key=ctx.llm_api_key,
                base_url=ctx.llm_base_url,
                model=ctx.llm_model,
                system="Summarize query results in 2-3 concise Chinese or English sentences.",
                user=(
                    f"Question: {question}\nSQL: {sql}\n"
                    f"Columns: {columns}\nRows sample: {preview_txt}"
                ),
                max_retries=ctx.llm_max_retries,
                retry_backoff_seconds=ctx.llm_retry_backoff_seconds,
                retry_backoff_max_seconds=ctx.llm_retry_backoff_max_seconds,
            )
            return result.content.strip(), result.as_step_llm()
        except LLMError:
            pass
    n = len(rows)
    return (
        f"Query returned {n} row(s) with columns {columns}. "
        f"Question: {question[:160]}",
        {"status": "skipped", "mode": "heuristic"},
    )


def _llm_chart_copy(
    ctx: AnalysisContext,
    *,
    question: str,
    summary: str,
    chart_type: str | None,
    fields: str | None,
    metric: str | None,
    old_title: str | None,
    **_: Any,
) -> tuple[str, str, dict[str, Any] | None]:
    result = chat_completion_result(
        api_key=ctx.llm_api_key,
        base_url=ctx.llm_base_url,
        model=ctx.llm_model,
        system=(
            "You write short chart titles. Reply with two lines only:\n"
            "TITLE: ...\nRATIONALE: ..."
        ),
        user=(
            f"Question: {question}\nSummary: {summary}\n"
            f"Chart type: {chart_type}\nX: {fields}\nY: {metric}\n"
            f"Old title: {old_title}"
        ),
        max_retries=ctx.llm_max_retries,
        retry_backoff_seconds=ctx.llm_retry_backoff_seconds,
        retry_backoff_max_seconds=ctx.llm_retry_backoff_max_seconds,
    )
    title = old_title or f"{metric} by {fields}"
    rationale = ""
    for line in result.content.splitlines():
        if line.upper().startswith("TITLE:"):
            title = line.split(":", 1)[1].strip() or title
        elif line.upper().startswith("RATIONALE:"):
            rationale = line.split(":", 1)[1].strip()
    return title, rationale, result.as_step_llm()


def _llm_report_markdown(
    ctx: AnalysisContext,
    *,
    question: str,
    summary: str,
    sql: str,
    columns: list[Any],
    row_count: int,
    chart_titles: list[str],
    limitations: list[str],
    **_: Any,
) -> tuple[str, dict[str, Any] | None]:
    result = chat_completion_result(
        api_key=ctx.llm_api_key,
        base_url=ctx.llm_base_url,
        model=ctx.llm_model,
        system=(
            "Write a short analysis brief in Markdown with headings "
            "## 结论, ## 关键发现, ## 局限与下一步. "
            "Do not invent numbers not present in the summary/SQL context. Max ~400 Chinese characters."
        ),
        user=(
            f"Question: {question}\nSummary: {summary}\nSQL: {sql}\n"
            f"Columns: {columns}\nRows: {row_count}\n"
            f"Charts: {chart_titles}\nLimitations: {limitations}"
        ),
        max_retries=ctx.llm_max_retries,
        retry_backoff_seconds=ctx.llm_retry_backoff_seconds,
        retry_backoff_max_seconds=ctx.llm_retry_backoff_max_seconds,
    )
    return result.content, result.as_step_llm()


def route_after_link(state: AnalysisState) -> str:
    if state.get("link_status") == "failed":
        return "fail"
    if state.get("hitl_execute_only"):
        return "validate_sql"
    return "generate_sql"


def hitl_plan_done(
    state: AnalysisState, *, ctx: AnalysisContext, sink: StepSink | None
) -> AnalysisState:
    """HITL H1: Gate-allowed SQL snapshot; execution deferred (no plane)."""
    checkpoint(ctx)
    sql = state.get("sql_final") or ""
    logger.info("HITL plan phase completed — awaiting human approval")
    lims = list(state.get("limitations") or [])
    note = "HITL: plan phase complete — awaiting human approval before execute."
    if note not in lims:
        lims.append(note)
    _emit(
        sink,
        StepRecord(
            node_name="hitl_plan_done",
            status="ok",
            input_json={"sql_final": sql},
            output_json={"hitl_plan_only": True, "deferred_execute": True},
            latency_ms=0,
        ),
    )
    return {
        **state,
        "status": "succeeded",
        "preview": {"columns": [], "rows": [], "row_count": 0},
        "summary": "SQL awaiting human approval (HITL plan phase).",
        "charts": [],
        "report": None,
        "limitations": lims,
        "error": "",
    }


def route_after_validate(state: AnalysisState) -> str:
    if state.get("gate_ok"):
        if state.get("hitl_plan_only"):
            return "hitl_plan_done"
        return "execute_sql"
    # HITL execute-only: never regenerate SQL after Gate deny
    if state.get("hitl_execute_only"):
        return "fail"
    # Non-repairable errors: fail immediately (policy_keyword, unknown, etc.)
    hint = state.get("repair_hint") or {}
    if hint.get("is_repairable") is False:
        return "fail"
    max_retries = int(state.get("max_retries") or 0)
    retry = int(state.get("retry_count") or 0)
    if retry <= max_retries:
        logger.info(
            "SQL repair retry triggered repair_class=%s retry=%d/%d",
            hint.get("repair_class", "unknown"), retry, max_retries,
        )
        return "generate_sql"
    logger.warning(
        "Max retries exceeded repair_class=%s retry=%d/%d",
        hint.get("repair_class", "unknown"), retry, max_retries,
    )
    return "fail"


def route_after_execute(state: AnalysisState) -> str:
    if state.get("preview") and not state.get("error"):
        return "summarize"
    # HITL execute-only: never regenerate SQL after execute failure
    if state.get("hitl_execute_only"):
        return "fail"
    # Non-repairable errors: fail immediately
    hint = state.get("repair_hint") or {}
    if hint.get("is_repairable") is False:
        return "fail"
    max_retries = int(state.get("max_retries") or 0)
    retry = int(state.get("retry_count") or 0)
    if retry <= max_retries:
        logger.info(
            "SQL execution repair retry triggered repair_class=%s retry=%d/%d",
            hint.get("repair_class", "unknown"), retry, max_retries,
        )
        return "generate_sql"
    logger.warning(
        "Max execution retries exceeded repair_class=%s retry=%d/%d",
        hint.get("repair_class", "unknown"), retry, max_retries,
    )
    return "fail"
