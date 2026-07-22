"""DuckDB analytics storage — import, schema inspection, preview.

Routes must not call DuckDB APIs directly; go through this module
(or dataset_service which orchestrates it).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import duckdb

from app.core.storage_paths import duckdb_path_for_workspace

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}


class DuckDBServiceError(Exception):
    """Raised for import / preview failures."""


def _quote_ident(name: str) -> str:
    if not name.replace("_", "").isalnum() or not name[0].isalpha() and name[0] != "_":
        raise DuckDBServiceError(f"Unsafe SQL identifier: {name!r}")
    return f'"{name}"'


def detect_extension(path: Path) -> str:
    ext = path.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise DuckDBServiceError(
            f"Unsupported file type {ext!r}. Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )
    return ext


def import_file(
    *,
    workspace_id: UUID,
    table_name: str,
    file_path: Path,
) -> dict[str, Any]:
    """Load CSV or first-sheet XLSX into DuckDB table. Returns schema + row_count."""
    path = Path(file_path)
    if not path.is_file():
        raise DuckDBServiceError(f"Upload file not found: {path}")

    ext = detect_extension(path)
    db_path = duckdb_path_for_workspace(workspace_id)
    table_sql = _quote_ident(table_name)
    # DuckDB file readers prefer absolute paths on Windows.
    file_sql = str(path.resolve()).replace("'", "''")

    con = duckdb.connect(str(db_path))
    try:
        con.execute(f"DROP TABLE IF EXISTS {table_sql}")
        if ext == ".csv":
            _strip_utf8_bom(path)
            con.execute(
                f"""
                CREATE TABLE {table_sql} AS
                SELECT * FROM read_csv_auto(
                    '{file_sql}',
                    HEADER=TRUE,
                    SAMPLE_SIZE=-1,
                    delim=',',
                    quote='"',
                    escape='"',
                    encoding='utf-8'
                )
                """
            )
        else:
            # First worksheet only (by name — DuckDB read_xlsx expects sheet name).
            from openpyxl import load_workbook

            workbook = load_workbook(path, read_only=True, data_only=True)
            try:
                if not workbook.sheetnames:
                    raise DuckDBServiceError("Excel workbook has no sheets")
                sheet_name = workbook.sheetnames[0]
            finally:
                workbook.close()
            sheet_sql = sheet_name.replace("'", "''")
            con.execute(
                f"""
                CREATE TABLE {table_sql} AS
                SELECT * FROM read_xlsx('{file_sql}', header=true, sheet='{sheet_sql}')
                """
            )

        schema = _read_schema(con, table_name)
        row_count = con.execute(f"SELECT COUNT(*) FROM {table_sql}").fetchone()[0]
        return {"schema": schema, "row_count": int(row_count)}
    except DuckDBServiceError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface engine errors cleanly
        raise DuckDBServiceError(str(exc)) from exc
    finally:
        con.close()


def preview_table(
    *,
    workspace_id: UUID,
    table_name: str,
    limit: int = 50,
) -> dict[str, Any]:
    """Return columns + row dicts for a registered table (controlled SELECT only)."""
    if limit < 1 or limit > 500:
        raise DuckDBServiceError("limit must be between 1 and 500")

    # Always go through Gate — even for preview-style SELECTs built here.
    table_sql = _quote_ident(table_name)
    sql = f"SELECT * FROM {table_sql} LIMIT {int(limit)}"
    return run_select(
        workspace_id=workspace_id,
        sql=sql,
        allowed_tables={table_name},
        default_limit=limit,
    )


def run_select(
    *,
    workspace_id: UUID,
    sql: str,
    allowed_tables: set[str],
    default_limit: int = 200,
) -> dict[str, Any]:
    """Execute analysis SQL only after SQL Gate validation (cannot be bypassed)."""
    from app.core.repo_path import ensure_repo_root_on_path

    ensure_repo_root_on_path()
    from agent.gates.sql_gate import validate_and_normalize_sql

    gate = validate_and_normalize_sql(
        sql,
        allowed_tables=allowed_tables,
        default_limit=default_limit,
    )
    if not gate.ok or not gate.sql:
        raise DuckDBServiceError(f"SQL Gate rejected query: {gate.error}")

    db_path = duckdb_path_for_workspace(workspace_id)
    if not db_path.is_file():
        raise DuckDBServiceError("DuckDB file not found for workspace")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        result = con.execute(gate.sql)
        columns = list(result.description) if result.description else []
        col_names = [c[0] for c in columns]
        raw_rows = result.fetchall()
        rows = [dict(zip(col_names, row, strict=True)) for row in raw_rows]
        safe_rows = [{k: _jsonable(v) for k, v in r.items()} for r in rows]
        return {
            "columns": col_names,
            "rows": safe_rows,
            "row_count": len(safe_rows),
            "sql": gate.sql,
        }
    except DuckDBServiceError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DuckDBServiceError(str(exc)) from exc
    finally:
        con.close()


def _read_schema(con: duckdb.DuckDBPyConnection, table_name: str) -> list[dict[str, str]]:
    rows = con.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = ?
        ORDER BY ordinal_position
        """,
        [table_name],
    ).fetchall()
    return [{"name": name, "type": dtype} for name, dtype in rows]


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _strip_utf8_bom(path: Path) -> None:
    """PowerShell / some editors write UTF-8 BOM which breaks CSV sniffing."""
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        path.write_bytes(data[3:])
