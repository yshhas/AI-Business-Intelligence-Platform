"""Eval fixture helpers — DuckDB / Postgres data-plane access."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

EVALS_ROOT = Path(__file__).resolve().parent


def _prepare_file_fixture(
    *,
    fixture_rel: str,
    workspace_id,
) -> tuple[str, list[dict[str, str]], int]:
    from app.core.storage_paths import ensure_storage_dirs
    from app.services import duckdb_service

    ensure_storage_dirs()
    csv_path = (EVALS_ROOT / fixture_rel).resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(f"Fixture missing: {csv_path}")
    table = f"ds_eval_{uuid4().hex[:12]}"
    imported = duckdb_service.import_file(
        workspace_id=workspace_id,
        table_name=table,
        file_path=csv_path,
    )
    schema = list(imported["schema"])
    row_count = int(imported["row_count"])
    return table, schema, row_count


def _execute_file(*, workspace_id, sql: str, table: str, default_limit: int) -> dict[str, Any]:
    from app.services import duckdb_service

    return duckdb_service.run_select(
        workspace_id=workspace_id,
        sql=sql,
        allowed_tables={table},
        default_limit=default_limit,
    )


def _execute_postgres(*, sql: str, allowed_tables: set[str], default_limit: int) -> dict[str, Any]:
    from app.services import postgres_ro_service

    return postgres_ro_service.run_select(
        sql=sql,
        allowed_tables=allowed_tables,
        default_limit=default_limit,
    )