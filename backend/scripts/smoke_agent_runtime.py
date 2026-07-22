"""Smoke: agent.runtime.run_analysis with heuristic SQL (no LLM)."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.core.repo_path import ensure_repo_root_on_path  # noqa: E402
from app.core.storage_paths import duckdb_path_for_workspace  # noqa: E402
from app.services.duckdb_service import run_select  # noqa: E402

ensure_repo_root_on_path()

from agent.runtime import run_analysis  # noqa: E402
from agent.state import AnalysisContext  # noqa: E402


def main() -> None:
    workspace_id = uuid4()
    table = "ds_smoke_phase4"
    db_path = duckdb_path_for_workspace(workspace_id)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))
    try:
        con.execute(f'DROP TABLE IF EXISTS "{table}"')
        con.execute(f'CREATE TABLE "{table}" (region VARCHAR, amount DOUBLE)')
        con.execute(
            f"""
            INSERT INTO "{table}" VALUES
              ('East', 100),
              ('West', 250),
              ('East', 50)
            """
        )
    finally:
        con.close()

    def execute_select(sql: str, limit: int):
        return run_select(
            workspace_id=workspace_id,
            sql=sql,
            allowed_tables={table},
            default_limit=limit,
        )

    ctx = AnalysisContext(
        workspace_id=workspace_id,
        dataset_id=uuid4(),
        question="按 region 汇总 amount 并排序",
        duckdb_table=table,
        schema=[
            {"name": "region", "type": "VARCHAR"},
            {"name": "amount", "type": "DOUBLE"},
        ],
        default_limit=50,
        max_retries=2,
        execute_select=execute_select,
        llm_api_key="",
        allow_heuristic_sql=True,
    )
    outcome = run_analysis(ctx)
    assert outcome.success, outcome.error_message
    assert outcome.result_json.get("mock") is False
    assert outcome.result_json.get("sql")
    preview = outcome.result_json.get("table_preview") or {}
    assert preview.get("rows"), preview
    charts = outcome.result_json.get("charts") or []
    assert isinstance(charts, list) and len(charts) >= 1, charts
    assert charts[0].get("type") in {"bar", "line"}
    report = outcome.result_json.get("report") or {}
    assert report.get("markdown"), report
    nodes = [s.node_name for s in outcome.steps]
    assert "validate_sql" in nodes and "execute_sql" in nodes
    assert "build_charts" in nodes and "write_report" in nodes
    print("AGENT_RUNTIME_OK")
    print("SQL:", outcome.result_json.get("sql"))
    print("ROWS:", preview.get("rows"))
    print("CHARTS:", len(charts), charts[0].get("type"), charts[0].get("title"))
    print("REPORT_TITLE:", report.get("title"))


if __name__ == "__main__":
    main()
