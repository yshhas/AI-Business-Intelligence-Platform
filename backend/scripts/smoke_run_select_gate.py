"""Smoke: DuckDB run_select must reject forbidden SQL via Gate."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.core.repo_path import ensure_repo_root_on_path  # noqa: E402

ensure_repo_root_on_path()

from app.services.duckdb_service import DuckDBServiceError, run_select  # noqa: E402


def main() -> None:
    ws = uuid4()
    try:
        run_select(
            workspace_id=ws,
            sql="DROP TABLE ds_x",
            allowed_tables={"ds_x"},
            default_limit=10,
        )
        raise SystemExit("EXPECTED_GATE_REJECT")
    except DuckDBServiceError as exc:
        msg = str(exc)
        assert "SQL Gate rejected" in msg or "Forbidden" in msg, msg

    print("RUN_SELECT_GATE_OK")


if __name__ == "__main__":
    main()
