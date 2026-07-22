"""Smoke tests for SQL Gate (no DuckDB / no LLM)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.gates.sql_gate import validate_and_normalize_sql  # noqa: E402


def main() -> None:
    allowed = {"ds_abc123"}

    ok = validate_and_normalize_sql(
        "SELECT region, SUM(amount) AS total FROM ds_abc123 GROUP BY region ORDER BY total DESC",
        allowed_tables=allowed,
        default_limit=100,
    )
    assert ok.ok and ok.sql and "LIMIT 100" in ok.sql.upper().replace("\n", " "), ok

    bad_drop = validate_and_normalize_sql(
        "DROP TABLE ds_abc123",
        allowed_tables=allowed,
    )
    assert not bad_drop.ok, bad_drop

    bad_table = validate_and_normalize_sql(
        "SELECT * FROM other_table",
        allowed_tables=allowed,
    )
    assert not bad_table.ok, bad_table

    bad_multi = validate_and_normalize_sql(
        "SELECT 1; SELECT 2",
        allowed_tables=allowed,
    )
    assert not bad_multi.ok, bad_multi

    print("GATE_OK")


if __name__ == "__main__":
    main()
