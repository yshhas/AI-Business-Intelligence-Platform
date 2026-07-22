"""Smoke: kernel.run(skill_id='data.bi') + Facade run_analysis."""

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

from agent.kernel.runtime import platform_info, run as kernel_run  # noqa: E402
from agent.kernel.types import RunRequest  # noqa: E402
from agent.runtime import run_analysis  # noqa: E402
from agent.state import AnalysisContext  # noqa: E402


def main() -> None:
    info = platform_info()
    assert any(s["skill_id"] == "data.bi" for s in info["skills"]), info
    assert any(s["skill_id"] == "data.profile" for s in info["skills"]), info
    bi = next(s for s in info["skills"] if s["skill_id"] == "data.bi")
    assert bi.get("version"), bi
    assert bi.get("enabled") is True, bi
    assert any(t["tool_id"] == "sql.execute_select" for t in info["tools"]), info
    assert any(p["policy_id"] == "sql.select_gate" for p in info["policies"]), info

    workspace_id = uuid4()
    dataset_id = uuid4()
    table = "ds_smoke_m1"
    db_path = duckdb_path_for_workspace(workspace_id)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        con.execute(f'DROP TABLE IF EXISTS "{table}"')
        con.execute(f'CREATE TABLE "{table}" (region VARCHAR, amount DOUBLE)')
        con.execute(
            f"INSERT INTO \"{table}\" VALUES ('East', 100), ('West', 250), ('East', 50)"
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

    req = RunRequest(
        skill_id="data.bi",
        workspace_id=workspace_id,
        input={"question": "按 region 汇总 amount", "dataset_id": str(dataset_id)},
        policy_context={
            "allowed_tables": [table],
            "default_limit": 50,
            "max_retries": 2,
        },
        runtime_hints={"llm_api_key": "", "allow_heuristic_sql": True},
        execute_select=execute_select,
        schema=[
            {"name": "region", "type": "VARCHAR"},
            {"name": "amount", "type": "DOUBLE"},
        ],
        duckdb_table=table,
    )
    result = kernel_run(req)
    assert result.success, result.error_message
    assert result.skill_id == "data.bi"
    assert any(a.type == "sql" for a in result.artifacts)
    assert any(a.type == "table" for a in result.artifacts)
    assert any(t.tool_id == "sql.execute_select" for t in result.tool_calls)
    assert any(p.policy_id == "sql.select_gate" and p.ok for p in result.policy_decisions)

    # Policy reject path
    bad = tool_policy_reject(execute_select, table)
    assert bad is True

    # Facade
    ctx = AnalysisContext(
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        question="按 region 汇总 amount",
        duckdb_table=table,
        schema=[
            {"name": "region", "type": "VARCHAR"},
            {"name": "amount", "type": "DOUBLE"},
        ],
        default_limit=50,
        max_retries=2,
        execute_select=execute_select,
        allow_heuristic_sql=True,
    )
    outcome = run_analysis(ctx)
    assert outcome.success, outcome.error_message
    assert outcome.result_json.get("platform", {}).get("skill_id") == "data.bi"
    assert outcome.result_json.get("sql")
    assert outcome.result_json.get("charts") is not None

    print("KERNEL_M1_OK")
    print("SKILL", result.skill_id)
    print("TOOLS", [t.tool_id for t in result.tool_calls])
    print("POLICIES", [p.policy_id for p in result.policy_decisions if p.ok])
    print("ARTIFACTS", [a.type for a in result.artifacts])


def tool_policy_reject(execute_select, table: str) -> bool:
    from agent.kernel.tools import tool_execute_select
    from agent.kernel.types import PolicyDecision, ToolCallRecord

    calls: list[ToolCallRecord] = []
    decisions: list[PolicyDecision] = []
    try:
        tool_execute_select(
            "DROP TABLE x",
            10,
            allowed_tables={table},
            default_limit=10,
            inner_execute=execute_select,
            tool_calls=calls,
            policy_decisions=decisions,
        )
        return False
    except RuntimeError:
        return any(not d.ok and d.policy_id == "sql.select_gate" for d in decisions)


if __name__ == "__main__":
    main()
