"""Smoke P0-2: Soft Cost Budget (workspace UTC-day enqueue gate).

Requires Postgres (+ Redis only if enqueue succeeds). Budget default 0 stays off.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

os.environ["LLM_TOKEN_BUDGET_PER_WORKSPACE_DAY"] = "100"
os.environ["ANALYSIS_QUEUE_KEY"] = f"aibi:budget_smoke_{uuid4().hex[:8]}"
# Keep capacity out of the way
os.environ["RUN_MAX_IN_FLIGHT"] = "20"
os.environ["ANALYSIS_QUEUE_MAX_DEPTH"] = "100"

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import AgentRunStep, AnalysisTask, Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import cost_budget  # noqa: E402
from app.services import run_lifecycle as rl  # noqa: E402
from app.services.cost_budget import BudgetError  # noqa: E402
from app.services.task_service import TaskServiceError, create_task  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.llm_token_budget_per_workspace_day == 100

    db = SessionLocal()
    try:
        email = f"budget_{uuid4().hex[:8]}@example.com"
        user = User(
            email=email,
            password_hash=hash_password("password123"),
            display_name="Budget",
        )
        db.add(user)
        db.flush()
        ws = Workspace(name="Budget WS", owner_user_id=user.id)
        db.add(ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
        ds = Dataset(
            workspace_id=ws.id,
            name="budget",
            source_type="file",
            original_filename="x.csv",
            storage_path="x",
            duckdb_table=f"ds_{uuid4().hex}",
            schema_json=[{"name": "a", "type": "INTEGER"}],
            row_count=0,
            status="ready",
            created_by=user.id,
            source_config_json={},
        )
        db.add(ds)
        db.commit()
        db.refresh(user)
        db.refresh(ws)
        db.refresh(ds)

        # --- Unit: usage extract ---
        assert cost_budget.tokens_from_usage_dict({"total_tokens": 42}) == 42
        assert cost_budget.tokens_from_usage_dict({"prompt_tokens": 10, "completion_tokens": 5}) == 15
        assert (
            cost_budget.extract_tokens_from_output_json(
                {"llm": {"usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}}}
            )
            == 7
        )

        # --- Budget off path: temporarily 0 ---
        os.environ["LLM_TOKEN_BUDGET_PER_WORKSPACE_DAY"] = "0"
        get_settings.cache_clear()
        cost_budget.assert_budget_allowed(db, workspace_id=ws.id, settings=get_settings())

        os.environ["LLM_TOKEN_BUDGET_PER_WORKSPACE_DAY"] = "100"
        get_settings.cache_clear()
        settings = get_settings()

        # --- Seed finished Run with tokens (under budget) ---
        prior = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="prior",
            status="succeeded",
            created_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            llm_total_tokens=40,
            skill_id="data.bi",
            skill_version="1.0.0",
        )
        db.add(prior)
        db.commit()
        used = cost_budget.workspace_day_token_usage(db, workspace_id=ws.id)
        assert used == 40, used

        # Still under budget → create ok
        ok_task = create_task(
            db,
            workspace_id=ws.id,
            user_id=user.id,
            dataset_id=ds.id,
            question="under budget",
            member_role="owner",
        )
        assert ok_task.status == "pending"
        assert ok_task.failure_class is None

        # Push usage to >= budget
        prior2 = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="fill",
            status="succeeded",
            created_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            llm_total_tokens=60,
            skill_id="data.bi",
        )
        db.add(prior2)
        db.commit()
        assert cost_budget.workspace_day_token_usage(db, workspace_id=ws.id) >= 100

        try:
            create_task(
                db,
                workspace_id=ws.id,
                user_id=user.id,
                dataset_id=ds.id,
                question="over budget",
                member_role="owner",
            )
            raise SystemExit("EXPECTED_BUDGET_REJECT")
        except TaskServiceError as exc:
            assert exc.status_code == 429, exc.status_code
            assert "budget" in str(exc).lower() or rl.FAILURE_BUDGET in str(exc)

        # Audit row exists
        rejected = db.scalars(
            select(AnalysisTask)
            .where(
                AnalysisTask.workspace_id == ws.id,
                AnalysisTask.failure_class == rl.FAILURE_BUDGET,
            )
            .order_by(AnalysisTask.created_at.desc())
        ).first()
        assert rejected is not None
        assert rejected.status == "failed"
        assert rejected.llm_total_tokens is None
        platform = (rejected.result_json or {}).get("platform") or {}
        assert (platform.get("run") or {}).get("failure_class") == rl.FAILURE_BUDGET

        # --- apply_llm_total_tokens from steps ---
        agg_task = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="agg",
            status="succeeded",
            finished_at=datetime.now(UTC),
            skill_id="data.bi",
        )
        db.add(agg_task)
        db.flush()
        db.add(
            AgentRunStep(
                task_id=agg_task.id,
                step_no=1,
                node_name="generate_sql",
                status="ok",
                output_json={
                    "llm": {
                        "usage": {
                            "prompt_tokens": 11,
                            "completion_tokens": 9,
                            "total_tokens": 20,
                        }
                    }
                },
            )
        )
        db.add(
            AgentRunStep(
                task_id=agg_task.id,
                step_no=2,
                node_name="write_report",
                status="ok",
                output_json={"llm": {"usage": {"total_tokens": 5}}},
            )
        )
        db.commit()
        db.refresh(agg_task)
        total = cost_budget.apply_llm_total_tokens(db, agg_task)
        db.add(agg_task)
        db.commit()
        db.refresh(agg_task)
        assert total == 25, total
        assert agg_task.llm_total_tokens == 25
        run_meta = ((agg_task.result_json or {}).get("platform") or {}).get("run") or {}
        # result_json may be None if never set — apply only echoes when present
        if agg_task.result_json:
            assert run_meta.get("llm_total_tokens") == 25

        # assert_budget_allowed raises BudgetError
        try:
            cost_budget.assert_budget_allowed(db, workspace_id=ws.id, settings=settings)
            raise SystemExit("EXPECTED_BUDGET_ERROR")
        except BudgetError as exc:
            assert exc.failure_class == rl.FAILURE_BUDGET

        print("P0_2_COST_BUDGET_OK")
    finally:
        db.close()
        # Restore default for other processes in same shell if any
        os.environ["LLM_TOKEN_BUDGET_PER_WORKSPACE_DAY"] = "0"
        get_settings.cache_clear()


if __name__ == "__main__":
    main()
