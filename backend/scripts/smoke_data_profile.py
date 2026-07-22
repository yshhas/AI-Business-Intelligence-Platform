"""Wave 3 smoke: data.profile Skill via same Kernel path as data.bi."""

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
    ids = {s["skill_id"] for s in info["skills"]}
    assert "data.bi" in ids and "data.profile" in ids, info
    profile = next(s for s in info["skills"] if s["skill_id"] == "data.profile")
    assert profile.get("enabled") is True, profile

    workspace_id = uuid4()
    dataset_id = uuid4()
    table = "ds_smoke_profile"
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
        skill_id="data.profile",
        workspace_id=workspace_id,
        input={"question": "profile", "dataset_id": str(dataset_id)},
        policy_context={"allowed_tables": [table], "default_limit": 50},
        execute_select=execute_select,
        schema=[
            {"name": "region", "type": "VARCHAR"},
            {"name": "amount", "type": "DOUBLE"},
        ],
        duckdb_table=table,
    )
    result = kernel_run(req)
    assert result.success, result.error_message
    assert result.skill_id == "data.profile"
    assert any(t.tool_id == "sql.execute_select" for t in result.tool_calls)
    assert any(p.policy_id == "sql.select_gate" and p.ok for p in result.policy_decisions)
    assert any(a.type == "table" for a in result.artifacts)
    table_art = next(a for a in result.artifacts if a.type == "table")
    assert table_art.payload.get("rows")

    # Policy reject still recorded for DROP
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
        raise AssertionError("DROP should fail gate")
    except RuntimeError:
        assert any(not d.ok for d in decisions)

    ctx = AnalysisContext(
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        question="profile",
        duckdb_table=table,
        schema=[
            {"name": "region", "type": "VARCHAR"},
            {"name": "amount", "type": "DOUBLE"},
        ],
        default_limit=50,
        max_retries=1,
        execute_select=execute_select,
        skill_id="data.profile",
    )
    outcome = run_analysis(ctx)
    assert outcome.success, outcome.error_message
    assert outcome.result_json.get("platform", {}).get("skill_id") == "data.profile"
    assert outcome.result_json.get("platform", {}).get("guardrails", {}).get("applied") is True

    print("DATA_PROFILE_SKILL_OK")


if __name__ == "__main__":
    main()
