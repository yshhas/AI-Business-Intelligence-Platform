"""MCP-style read-only tool invoke (Wave 3 MVP) — HTTP adapter, not a full MCP server.

All SQL-related tools must pass sql.select_gate. Shell-authenticated only.
Stabilization: allowlists come from Dataset ACL projection — never from caller alone.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.repo_path import ensure_repo_root_on_path
from app.services import dataset_service
from app.services.dataset_service import DatasetServiceError


class McpError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def list_tools() -> list[dict[str, str]]:
    return [
        {
            "name": "sql.gate_validate",
            "description": "Validate SELECT SQL against Policy Gate using dataset ACL allowlist (no execute)",
        },
        {
            "name": "dataset.schema_get",
            "description": "Read dataset schema_json + ACL-projected allowlist (no raw DSN)",
        },
    ]


def invoke_tool(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> dict[str, Any]:
    args = arguments or {}
    if tool_name == "sql.gate_validate":
        return _gate_validate(db, workspace_id=workspace_id, user_id=user_id, args=args)
    if tool_name == "dataset.schema_get":
        return _schema_get(db, workspace_id=workspace_id, user_id=user_id, args=args)
    raise McpError(f"Unknown tool {tool_name!r}", status_code=404)


def _load_dataset(
    db: Session, *, workspace_id: UUID, args: dict[str, Any]
):
    dataset_id = args.get("dataset_id")
    if not dataset_id:
        raise McpError("dataset_id required", status_code=400)
    try:
        ds = dataset_service.get_dataset(
            db, workspace_id=workspace_id, dataset_id=UUID(str(dataset_id))
        )
    except (TypeError, ValueError) as exc:
        raise McpError("invalid dataset_id", status_code=400) from exc
    if ds is None:
        raise McpError("Dataset not found", status_code=404)
    return ds


def _gate_validate(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    args: dict[str, Any],
) -> dict[str, Any]:
    ensure_repo_root_on_path()
    from agent.gates.sql_gate import validate_and_normalize_sql

    ds = _load_dataset(db, workspace_id=workspace_id, args=args)
    sql = str(args.get("sql") or "")
    try:
        allowed = dataset_service.allowed_tables_for(ds, db=db, user_id=user_id)
    except DatasetServiceError as exc:
        raise McpError(str(exc), status_code=exc.status_code) from exc
    limit = int(args.get("default_limit") or 200)
    decision = validate_and_normalize_sql(
        sql, allowed_tables=set(allowed), default_limit=limit
    )
    return {
        "ok": bool(decision.ok),
        "sql": decision.sql if decision.ok else None,
        "error": decision.error,
        "policy_id": "sql.select_gate",
        "allowed_tables": sorted(allowed),
    }


def _schema_get(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    args: dict[str, Any],
) -> dict[str, Any]:
    ds = _load_dataset(db, workspace_id=workspace_id, args=args)
    try:
        allowed = sorted(
            dataset_service.allowed_tables_for(ds, db=db, user_id=user_id)
        )
    except DatasetServiceError as exc:
        raise McpError(str(exc), status_code=exc.status_code) from exc
    return {
        "dataset_id": str(ds.id),
        "name": ds.name,
        "source_type": ds.source_type,
        "primary_relation": ds.duckdb_table,
        "allowed_tables": allowed,
        "schema": list(ds.schema_json or []),
        "status": ds.status,
    }
