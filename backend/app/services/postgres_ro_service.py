"""Postgres read-only select executor (M3) — Product Shell only, not Kernel.

DSN from settings.postgres_ro_dsn (env POSTGRES_RO_DSN). Never logs credentials.
Always re-applies SQL Gate and forces a read-only transaction.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.core.config import get_settings
from app.core.repo_path import ensure_repo_root_on_path

# Fixed Demo schema for M3 (no multi-schema product).
POSTGRES_RO_SCHEMA = "public"
MAX_ALLOWED_TABLES = 2


class ConnectorError(Exception):
    """Infrastructure / connection failures for the RO data plane.

    Messages are prefixed so run_lifecycle.classify_exception → connector_error.
    """

    def __init__(self, message: str) -> None:
        super().__init__(f"Connector error: {message}")


def normalize_relation(name: str) -> str:
    """Require schema-qualified public.table (lowercase normalized form)."""
    raw = (name or "").strip().strip('"')
    if raw.count(".") != 1:
        raise ConnectorError(
            f"Relation must be schema-qualified as {POSTGRES_RO_SCHEMA}.table "
            f"(got {name!r})"
        )
    schema, table = raw.split(".", 1)
    schema = schema.strip().strip('"').lower()
    table = table.strip().strip('"').lower()
    if schema != POSTGRES_RO_SCHEMA:
        raise ConnectorError(
            f"Only schema {POSTGRES_RO_SCHEMA!r} is allowed (got {schema!r})"
        )
    if not table or not table.replace("_", "").isalnum() or table[0].isdigit():
        raise ConnectorError(f"Invalid table name {table!r}")
    return f"{schema}.{table}"


def normalize_allowlist(tables: list[str]) -> list[str]:
    if not tables:
        raise ConnectorError("At least one allowlisted table is required")
    if len(tables) > MAX_ALLOWED_TABLES:
        raise ConnectorError(
            f"At most {MAX_ALLOWED_TABLES} tables allowed in M3 (got {len(tables)})"
        )
    out: list[str] = []
    seen: set[str] = set()
    for t in tables:
        n = normalize_relation(t)
        if n not in seen:
            out.append(n)
            seen.add(n)
    return out


def _dsn() -> str:
    settings = get_settings()
    dsn = (settings.postgres_ro_dsn or "").strip()
    if not dsn:
        raise ConnectorError("POSTGRES_RO_DSN is not configured")
    return dsn


def _connect_ro():
    """Open connection and force read-only session."""
    try:
        conn = psycopg.connect(_dsn(), connect_timeout=8)
    except Exception as exc:  # noqa: BLE001
        raise ConnectorError(f"failed to connect to read-only data source: {exc}") from exc
    try:
        conn.execute("SET default_transaction_read_only = on")
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    except Exception as exc:  # noqa: BLE001
        conn.close()
        raise ConnectorError(f"failed to enable read-only session: {exc}") from exc
    return conn


def probe_and_describe(allowed_tables: list[str]) -> dict[str, Any]:
    """Validate DSN + SELECT privilege; return primary schema snapshot + row_count."""
    tables = normalize_allowlist(allowed_tables)
    primary = tables[0]
    schema_name, table_name = primary.split(".", 1)

    conn = _connect_ro()
    try:
        for rel in tables:
            sch, tbl = rel.split(".", 1)
            row = conn.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
                """,
                (sch, tbl),
            ).fetchone()
            if row is None:
                raise ConnectorError(f"relation {rel} does not exist")
            try:
                conn.execute(f'SELECT 1 FROM "{sch}"."{tbl}" LIMIT 1')
            except Exception as exc:  # noqa: BLE001
                raise ConnectorError(f"cannot SELECT from {rel}: {exc}") from exc

        cols = conn.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema_name, table_name),
        ).fetchall()
        schema_json = [{"name": r[0], "type": r[1]} for r in cols]
        count_row = conn.execute(
            f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}"'
        ).fetchone()
        row_count = int(count_row[0]) if count_row else 0
        return {
            "allowed_tables": tables,
            "primary_table": primary,
            "schema": schema_json,
            "row_count": row_count,
        }
    finally:
        conn.close()


def run_select(
    *,
    sql: str,
    allowed_tables: set[str],
    default_limit: int = 200,
) -> dict[str, Any]:
    """Execute analysis SQL after Gate; Gate fails → RuntimeError (policy_denied)."""
    ensure_repo_root_on_path()
    from agent.gates.sql_gate import validate_and_normalize_sql

    normalized = {normalize_relation(t) for t in allowed_tables}
    gate = validate_and_normalize_sql(
        sql,
        allowed_tables=normalized,
        default_limit=default_limit,
    )
    if not gate.ok or not gate.sql:
        raise RuntimeError(f"SQL Gate rejected query: {gate.error}")

    conn = _connect_ro()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(gate.sql)
            raw_rows = cur.fetchall()
            col_names = [d.name for d in cur.description] if cur.description else []
        rows = [{k: _jsonable(v) for k, v in dict(r).items()} for r in raw_rows]
        return {
            "columns": col_names,
            "rows": rows,
            "row_count": len(rows),
            "sql": gate.sql,
        }
    except RuntimeError:
        raise
    except ConnectorError:
        raise
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "read-only" in msg or "read only" in msg:
            raise ConnectorError(f"write blocked by read-only session: {exc}") from exc
        raise ConnectorError(f"query failed: {exc}") from exc
    finally:
        conn.close()


def preview_table(
    *,
    primary_table: str,
    allowed_tables: set[str],
    limit: int = 50,
) -> dict[str, Any]:
    if limit < 1 or limit > 500:
        raise ConnectorError("limit must be between 1 and 500")
    rel = normalize_relation(primary_table)
    sch, tbl = rel.split(".", 1)
    sql = f'SELECT * FROM "{sch}"."{tbl}" LIMIT {int(limit)}'
    return run_select(
        sql=sql,
        allowed_tables=allowed_tables,
        default_limit=limit,
    )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
