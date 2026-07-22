"""Smoke E2: Analyze explainability — Trace API exposes sql_quality (no new storage).

Verifies:
  - ExecutionTraceOut includes sql_quality when present on result_json.platform
  - authorization still present
  - no duplicate Trace model — projection only

Usage (from backend/):
  python scripts/smoke_e2_explainability.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import AnalysisTask, Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.schemas.task import ExecutionTraceOut  # noqa: E402
from app.services import run_lifecycle as rl  # noqa: E402
from app.services.task_service import get_execution_trace  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    db = SessionLocal()
    try:
        email = f"e2_{uuid4().hex[:8]}@example.com"
        user = User(
            email=email,
            password_hash=hash_password("password123"),
            display_name="E2",
        )
        db.add(user)
        db.flush()
        ws = Workspace(name="E2 WS", owner_user_id=user.id)
        db.add(ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
        table = f"ds_e2_{uuid4().hex[:8]}"
        ds = Dataset(
            workspace_id=ws.id,
            name="e2",
            source_type="file",
            original_filename="x.csv",
            storage_path="x",
            duckdb_table=table,
            schema_json=[{"name": "region", "type": "VARCHAR"}, {"name": "amount", "type": "DOUBLE"}],
            row_count=2,
            status="ready",
            created_by=user.id,
            source_config_json={},
        )
        db.add(ds)
        db.flush()

        sql_quality = {
            "schema_version": 1,
            "link_status": "fallback_full",
            "link_method": "fallback_full",
            "link_reason": "no_token_overlap",
            "selected_tables": [table],
            "selected_columns": ["region", "amount"],
            "column_count_full": 10,
            "column_count_linked": 2,
        }
        authorization = {
            "actor_user_id": str(user.id),
            "actor_role": "owner",
            "dataset_id": str(ds.id),
            "authorized_tables": [table],
            "acl_mode": "empty_acl",
        }
        result_json = {
            "summary": "e2 smoke",
            "sql": f'SELECT region FROM "{table}"',
            "platform": {
                "skill_id": "data.bi",
                "skill_version": "0.1.0",
                "sql_quality": sql_quality,
                "authorization": authorization,
                "data_plane": {"source_type": "file", "table": table},
                "execution": {
                    "schema_version": 1,
                    "tool_calls": [],
                    "policy_decisions": [
                        {
                            "decision_id": "pd_1",
                            "policy_id": "sql.select_gate",
                            "ok": False,
                            "reason": "Smoke deny reason",
                            "tool_id": "sql.validate_policy",
                        }
                    ],
                    "artifacts": [{"artifact_id": "a1", "type": "sql", "status": "ready"}],
                    "summary": {
                        "tool_count": 0,
                        "policy_decision_count": 1,
                        "policy_deny_count": 1,
                        "artifact_count": 1,
                        "artifact_types": ["sql"],
                        "incomplete": True,
                    },
                },
            },
            "limitations": [],
            "mock": False,
        }

        task = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="e2 explainability smoke",
            status="failed",
            result_json=result_json,
            error_message="Smoke deny reason",
            failure_class=rl.FAILURE_POLICY,
            policy_denied=True,
            skill_id="data.bi",
            skill_version="0.1.0",
            source_type="file",
            llm_total_tokens=42,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        raw = get_execution_trace(db, workspace_id=ws.id, task_id=task.id)
        assert raw is not None
        assert raw.get("sql_quality") is not None, "service must project sql_quality"
        assert raw["sql_quality"]["link_status"] == "fallback_full"
        assert raw["authorization"]["actor_role"] == "owner"

        # OpenAPI model must not strip sql_quality
        out = ExecutionTraceOut.model_validate(raw)
        assert out.sql_quality is not None
        assert out.sql_quality["link_status"] == "fallback_full"
        assert out.sql_quality["link_method"] == "fallback_full"
        assert out.authorization is not None
        assert out.authorization["authorized_tables"] == [table]
        assert out.policy_denied is True
        assert out.failure_class == rl.FAILURE_POLICY
        deny = (out.execution.get("policy_decisions") or [None])[0]
        assert deny and deny.get("ok") is False
        assert deny.get("reason") == "Smoke deny reason"

        print("E2: ExecutionTraceOut.sql_quality preserved (fallback_full visible)")
        print("E2: authorization + policy deny reason present")
        print("E2_EXPLAINABILITY_OK")
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"E2_EXPLAINABILITY_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
