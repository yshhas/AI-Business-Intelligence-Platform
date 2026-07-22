"""MySQL read-only select executor (Wave 3 MVP) — optional plane when MYSQL_RO_DSN set.

Mirrors postgres_ro: Product Shell only; always re-applies SQL Gate; read-only session.
Requires PyMySQL. Schema-qualified as db.table (database from DSN if unqualified).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.repo_path import ensure_repo_root_on_path

MAX_ALLOWED_TABLES = 2


class ConnectorError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(f"Connector error: {message}")


def _dsn() -> str:
    settings = get_settings()
    dsn = (settings.mysql_ro_dsn or "").strip()
    if not dsn:
        raise ConnectorError("MYSQL_RO_DSN is not configured")
    return dsn


def _default_database() -> str:
    parsed = urlparse(_dsn())
    db = (parsed.path or "").lstrip("/").split("?")[0].strip()
    if not db:
        raise ConnectorError("MYSQL_RO_DSN must include a database path")
    return db


def normalize_relation(name: str) -> str:
    raw = (name or "").strip().strip("`").strip('"')
    if raw.count(".") == 0:
        raw = f"{_default_database()}.{raw}"
    if raw.count(".") != 1:
        raise ConnectorError(f"Relation must be database.table (got {name!r})")
    schema, table = raw.split(".", 1)
    schema = schema.strip().strip("`").strip('"').lower()
    table = table.strip().strip("`").strip('"').lower()
    if not schema or not table:
        raise ConnectorError(f"Invalid relation {name!r}")
    if not table.replace("_", "").isalnum() or table[0].isdigit():
        raise ConnectorError(f"Invalid table name {table!r}")
    return f"{schema}.{table}"


def normalize_allowlist(tables: list[str]) -> list[str]:
    if not tables:
        raise ConnectorError("At least one allowlisted table is required")
    if len(tables) > MAX_ALLOWED_TABLES:
        raise ConnectorError(
            f"At most {MAX_ALLOWED_TABLES} tables allowed (got {len(tables)})"
        )
    out: list[str] = []
    seen: set[str] = set()
    for t in tables:
        n = normalize_relation(t)
        if n not in seen:
            out.append(n)
            seen.add(n)
    return out


def _connect():
    try:
        import pymysql
    except ImportError as exc:
        raise ConnectorError("PyMySQL is required for mysql_ro (pip install PyMySQL)") from exc
    dsn = _dsn()
    parsed = urlparse(dsn)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise ConnectorError("MYSQL_RO_DSN must use mysql:// scheme")
    try:
        conn = pymysql.connect(
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 3306,
            user=parsed.username or "",
            password=parsed.password or "",
            database=(parsed.path or "").lstrip("/").split("?")[0] or None,
            connect_timeout=8,
            read_timeout=30,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
        with conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.execute("START TRANSACTION READ ONLY")
        return conn
    except ConnectorError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ConnectorError(f"MySQL connect failed: {exc}") from exc


def probe_tables(tables: list[str]) -> dict[str, Any]:
    allowed = normalize_allowlist(tables)
    conn = _connect()
    try:
        schema_cols: list[dict[str, Any]] = []
        primary = allowed[0]
        db_name, table = primary.split(".", 1)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COLUMN_NAME AS name, DATA_TYPE AS type
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
                ORDER BY ORDINAL_POSITION
                """,
                (db_name, table),
            )
            rows = cur.fetchall() or []
            for r in rows:
                schema_cols.append({"name": r["name"], "type": str(r["type"]).upper()})
            cur.execute(f"SELECT COUNT(*) AS n FROM `{db_name}`.`{table}`")
            count_row = cur.fetchone() or {"n": 0}
            row_count = int(count_row.get("n") or 0)
        return {
            "allowed_tables": allowed,
            "primary_table": primary,
            "schema_json": schema_cols,
            "row_count": row_count,
        }
    finally:
        conn.close()


def run_select(
    sql: str,
    *,
    allowed_tables: set[str],
    default_limit: int,
) -> dict[str, Any]:
    ensure_repo_root_on_path()
    from agent.gates.sql_gate import validate_and_normalize_sql

    allowed = normalize_allowlist(sorted(allowed_tables))
    gate = validate_and_normalize_sql(
        sql,
        allowed_tables=set(allowed),
        default_limit=default_limit or 200,
    )
    if not gate.ok or not gate.sql:
        raise RuntimeError(f"SQL Gate rejected query: {gate.error}")

    final_sql = gate.sql
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(final_sql)
            rows_dicts = cur.fetchall() or []
            columns = list(rows_dicts[0].keys()) if rows_dicts else [
                d[0] for d in (cur.description or [])
            ]
            # Match DuckDB/Postgres plane: list[dict] for charts / profile skill
            rows = [{c: r.get(c) for c in columns} for r in rows_dicts]
        return {"columns": columns, "rows": rows, "row_count": len(rows)}
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ConnectorError(f"MySQL select failed: {exc}") from exc
    finally:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        conn.close()
