"""Phase 4 agent analysis runtime adapter for the worker.

Builds AnalysisContext and calls `agent.runtime.run_analysis` only.
Persists AgentRunStep rows from the outcome (agent does not use SQLAlchemy).

M3/Wave3: branches execute_select on Dataset.source_type (file | postgres_ro | mysql_ro).
M4: always materializes platform.execution; failures carry partial result_json.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.repo_path import ensure_repo_root_on_path
from app.models import AgentRunStep, AnalysisTask, Dataset, WorkspaceMember
from app.services import dataset_service, duckdb_service, permissions as perm, postgres_ro_service
from app.services.postgres_ro_service import ConnectorError


class AgentAnalysisError(RuntimeError):
    """Skill failed but may still carry a partial Execution Trace."""

    def __init__(self, message: str, *, result_json: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.result_json = result_json or {}


def run_agent_analysis(
    db: Session,
    task: AnalysisTask,
    settings: Settings,
    *,
    cancel_check: Any | None = None,
    token: Any | None = None,
) -> dict[str, Any]:
    ensure_repo_root_on_path()
    from agent.runtime import run_analysis
    from agent.run_control import RunAborted
    from agent.state import AnalysisContext
    from app.workers.write_fence import write_allowed

    dataset = db.get(Dataset, task.dataset_id)
    if dataset is None:
        raise RuntimeError(f"Dataset {task.dataset_id} not found")
    if dataset.status != "ready":
        raise RuntimeError(f"Dataset status is {dataset.status!r}, expected ready")

    workspace_id: UUID = task.workspace_id
    table = dataset.duckdb_table
    schema = list(dataset.schema_json or [])
    default_limit = settings.sql_default_limit
    skill_id = (task.skill_id or "data.bi").strip() or "data.bi"

    try:
        allowed = dataset_service.allowed_tables_for(
            dataset, db=db, user_id=task.user_id
        )
    except dataset_service.DatasetServiceError as exc:
        raise ConnectorError(str(exc)) from exc

    if dataset.source_type == "file":

        def execute_select(sql: str, limit: int) -> dict[str, Any]:
            return duckdb_service.run_select(
                workspace_id=workspace_id,
                sql=sql,
                allowed_tables=allowed,
                default_limit=limit or default_limit,
            )

    elif dataset.source_type == "postgres_ro":

        def execute_select(sql: str, limit: int) -> dict[str, Any]:
            return postgres_ro_service.run_select(
                sql=sql,
                allowed_tables=allowed,
                default_limit=limit or default_limit,
            )

    elif dataset.source_type == "mysql_ro":
        from app.services import mysql_ro_service

        def execute_select(sql: str, limit: int) -> dict[str, Any]:
            return mysql_ro_service.run_select(
                sql,
                allowed_tables=allowed,
                default_limit=limit or default_limit,
            )

    else:
        raise ConnectorError(f"unsupported source_type={dataset.source_type!r}")

    synonyms: dict[str, list[str]] = {}
    cfg = dataset.source_config_json if isinstance(dataset.source_config_json, dict) else {}
    raw_syn = cfg.get("synonyms") if isinstance(cfg, dict) else None
    if isinstance(raw_syn, dict):
        synonyms.update(
            {
                str(k): [str(x) for x in (v or [])]
                for k, v in raw_syn.items()
                if isinstance(v, (list, tuple))
            }
        )
    if settings.workspace_memory_enabled:
        from app.services import workspace_memory as wmem

        mem = wmem.load_synonyms(
            db, workspace_id=workspace_id, dataset_id=dataset.id
        )
        for phrase, cols in mem.items():
            existing = synonyms.get(phrase, [])
            synonyms[phrase] = list(dict.fromkeys([*existing, *cols]))

    from agent.llm_providers import resolve_llm_config

    llm_base_url, llm_model = resolve_llm_config(
        settings.llm_provider,
        settings.llm_base_url,
        settings.llm_model,
    )

    ctx = AnalysisContext(
        workspace_id=workspace_id,
        dataset_id=task.dataset_id,
        question=task.question,
        duckdb_table=table,
        schema=schema,
        default_limit=default_limit,
        max_retries=settings.sql_max_retries,
        execute_select=execute_select,
        skill_id=skill_id,
        llm_api_key=settings.llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        allow_heuristic_sql=settings.allow_heuristic_sql,
        allowed_tables=sorted(allowed),
        source_type=dataset.source_type,
        schema_synonyms=synonyms or None,
        llm_max_retries=settings.llm_max_retries,
        llm_retry_backoff_seconds=settings.llm_retry_backoff_seconds,
        llm_retry_backoff_max_seconds=settings.llm_retry_backoff_max_seconds,
        cancel_check=cancel_check,
    )

    try:
        outcome = run_analysis(ctx)
    except RunAborted:
        raise

    if not write_allowed(db, task.id, token):
        raise RunAborted(token.reason() if token and token.reason() else "cancelled")

    for idx, step in enumerate(outcome.steps, start=1):
        if not write_allowed(db, task.id, token):
            break
        db.add(
            AgentRunStep(
                task_id=task.id,
                step_no=idx,
                node_name=step.node_name,
                status=step.status,
                input_json=step.input_json,
                output_json=step.output_json,
                error_message=step.error_message,
                latency_ms=step.latency_ms,
            )
        )
    db.flush()

    result = dict(outcome.result_json or {})
    result["task_id"] = str(task.id)
    platform = dict(result.get("platform") or {})
    platform["data_plane"] = {
        "source_type": dataset.source_type,
        "primary_table": table,
        "allowed_tables": sorted(allowed),
    }
    # P1: audit-only authorization snapshot (not a permission cache)
    member = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == task.workspace_id,
            WorkspaceMember.user_id == task.user_id,
        )
    ).scalar_one_or_none()
    actor_role = member.role if member is not None else "unknown"
    platform["authorization"] = perm.build_authorization_snapshot(
        actor_user_id=task.user_id,
        actor_role=actor_role,
        dataset=dataset,
        authorized_tables=sorted(allowed),
        acl_mode=perm.acl_mode_for_dataset(db, dataset.id),
    )
    if outcome.success:
        platform.setdefault("skill_id", skill_id)
    if task.skill_version:
        platform.setdefault("skill_version", task.skill_version)
    elif platform.get("skill_id") and not platform.get("skill_version"):
        from app.services import skill_lifecycle as skills

        skills.sync_from_settings(settings)
        from agent.kernel import registry

        meta = registry.get_skill_meta(str(platform.get("skill_id") or skill_id))
        if meta:
            platform["skill_version"] = meta.version
    result["platform"] = platform

    if outcome.success and settings.workspace_memory_enabled and skill_id == "data.bi":
        if write_allowed(db, task.id, token):
            try:
                from app.services import workspace_memory as wmem

                selected: list[str] = []
                sq = (platform.get("sql_quality") or {}) if isinstance(platform, dict) else {}
                if isinstance(sq, dict):
                    selected = [str(c) for c in (sq.get("selected_columns") or []) if c]
                if selected:
                    wmem.remember_from_link(
                        db,
                        workspace_id=workspace_id,
                        dataset_id=dataset.id,
                        question=task.question,
                        selected_columns=selected,
                    )
                    db.flush()
            except Exception:  # noqa: BLE001 — memory must not fail the Run
                pass

    if not write_allowed(db, task.id, token):
        raise RunAborted(token.reason() if token and token.reason() else "cancelled")

    if not outcome.success:
        raise AgentAnalysisError(
            outcome.error_message or "Agent analysis failed",
            result_json=result,
        )

    return result
