"""Deterministic SQL Gate — no LLM.

Used by duckdb_service.run_select AND agent validate_sql node.
Never execute analysis SQL without passing this gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sqlparse
from sqlparse.tokens import DML, Keyword

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|"
    r"COPY|EXPORT|IMPORT|PRAGMA|INSTALL|LOAD|CALL|EXECUTE|GRANT|REVOKE|"
    r"VACUUM|CHECKPOINT|MERGE|UPSERT)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GateResult:
    ok: bool
    sql: str | None
    error: str | None = None


def validate_and_normalize_sql(
    sql: str,
    *,
    allowed_tables: set[str],
    default_limit: int = 200,
) -> GateResult:
    if not sql or not sql.strip():
        return GateResult(ok=False, sql=None, error="Empty SQL")

    cleaned = sql.strip().rstrip(";").strip()
    if ";" in cleaned:
        return GateResult(ok=False, sql=None, error="Multiple statements are not allowed")

    if _FORBIDDEN.search(cleaned):
        return GateResult(ok=False, sql=None, error="Forbidden keyword detected (write/DDL/admin)")

    parsed = sqlparse.parse(cleaned)
    if not parsed:
        return GateResult(ok=False, sql=None, error="Failed to parse SQL")
    if len(parsed) != 1:
        return GateResult(ok=False, sql=None, error="Only a single statement is allowed")

    stmt = parsed[0]
    first_dml = None
    for token in stmt.tokens:
        if token.is_whitespace:
            continue
        if token.ttype is DML:
            first_dml = token.value.upper()
            break
        if token.ttype is Keyword and token.value.upper() == "WITH":
            first_dml = "WITH"
            break
        # Skip comments / punctuation
        if getattr(token, "is_group", False):
            continue

    if first_dml not in {"SELECT", "WITH"}:
        return GateResult(
            ok=False,
            sql=None,
            error=f"Only SELECT/WITH queries are allowed (got {first_dml!r})",
        )

    referenced = _extract_table_names(cleaned)
    if not referenced:
        return GateResult(ok=False, sql=None, error="Could not resolve table name from SQL")

    allowed_lower = {t.lower() for t in allowed_tables}
    for table in referenced:
        if table.lower() not in allowed_lower:
            return GateResult(
                ok=False,
                sql=None,
                error=f"Table {table!r} is not in allowlist {sorted(allowed_tables)}",
            )

    final_sql = cleaned
    if not re.search(r"\blimit\s+\d+\b", final_sql, flags=re.IGNORECASE):
        final_sql = f"{final_sql}\nLIMIT {int(default_limit)}"

    return GateResult(ok=True, sql=final_sql, error=None)


def _extract_table_names(sql: str) -> set[str]:
    """Best-effort table extraction from FROM/JOIN clauses.

    Supports bare names (DuckDB `ds_*`) and schema-qualified names
    (`public.demo_orders`) required for M3 Postgres RO allowlists.
    """
    tables: set[str] = set()
    pattern = re.compile(
        r"\b(?:FROM|JOIN)\s+"
        r"(?:"
        r"(?P<q1>[\"`]?)(?P<schema>[A-Za-z_][A-Za-z0-9_]*)(?P=q1)\s*\.\s*"
        r")?"
        r"(?P<q2>[\"`]?)(?P<table>[A-Za-z_][A-Za-z0-9_]*)(?P=q2)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(sql):
        schema = match.group("schema")
        table = match.group("table")
        if schema:
            tables.add(f"{schema}.{table}")
        else:
            tables.add(table)
    return tables
