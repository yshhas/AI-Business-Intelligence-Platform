"""Smoke M3: postgres_ro bind + Policy allowlist + connector_error + heuristic run.

Requires: platform Postgres, Redis optional (direct runtime), postgres_ro fixture,
POSTGRES_RO_DSN set, Alembic 0005 applied.
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
from app.models import Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import dataset_service, postgres_ro_service, run_lifecycle as rl  # noqa: E402
from app.services.postgres_ro_service import ConnectorError  # noqa: E402
from agent.gates.sql_gate import validate_and_normalize_sql  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.postgres_ro_dsn, "POSTGRES_RO_DSN must be set"

    # --- Gate: schema-qualified allowlist ---
    allowed = {"public.demo_orders", "public.demo_customers"}
    ok = validate_and_normalize_sql(
        "SELECT amount FROM public.demo_orders",
        allowed_tables=allowed,
        default_limit=10,
    )
    assert ok.ok, ok.error

    denied = validate_and_normalize_sql(
        "SELECT * FROM public.secret_table",
        allowed_tables=allowed,
        default_limit=10,
    )
    assert not denied.ok
    assert "allowlist" in (denied.error or "").lower()

    bare = validate_and_normalize_sql(
        "SELECT * FROM demo_orders",
        allowed_tables=allowed,
        default_limit=10,
    )
    assert not bare.ok, "bare table names must fail against public.* allowlist"

    # --- Live probe ---
    probed = postgres_ro_service.probe_and_describe(
        ["public.demo_orders", "public.demo_customers"]
    )
    assert probed["primary_table"] == "public.demo_orders"
    assert len(probed["allowed_tables"]) == 2

    preview = postgres_ro_service.run_select(
        sql='SELECT product, amount FROM public.demo_orders ORDER BY order_id',
        allowed_tables=set(probed["allowed_tables"]),
        default_limit=5,
    )
    assert preview["row_count"] >= 1

    # Policy deny does not become connector_error
    try:
        postgres_ro_service.run_select(
            sql="SELECT * FROM public.not_allowed",
            allowed_tables=set(probed["allowed_tables"]),
            default_limit=5,
        )
        raise AssertionError("expected Gate reject")
    except RuntimeError as exc:
        assert "sql gate rejected" in str(exc).lower()
        assert rl.classify_exception(exc) == rl.FAILURE_POLICY

    # connector_error classification
    assert (
        rl.classify_exception(ConnectorError("failed to connect"))
        == rl.FAILURE_CONNECTOR
    )

    db = SessionLocal()
    try:
        email = f"m3_{uuid4().hex[:8]}@example.com"
        user = User(
            email=email,
            password_hash=hash_password("password123"),
            display_name="M3",
        )
        db.add(user)
        db.flush()
        ws = Workspace(name="M3 WS", owner_user_id=user.id)
        db.add(ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
        db.commit()

        ds = dataset_service.create_dataset_from_postgres_ro(
            db,
            workspace_id=ws.id,
            user_id=user.id,
            name="M3 RO Demo",
            tables=["public.demo_orders", "public.demo_customers"],
        )
        assert ds.source_type == "postgres_ro"
        assert ds.duckdb_table == "public.demo_orders"
        assert ds.status == "ready"

        # Heuristic skill path via agent_runtime shape
        from app.workers.agent_runtime import run_agent_analysis
        from app.models import AnalysisTask

        task = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="按 product 汇总 amount",
            status="running",
            timeout_seconds=settings.run_timeout_seconds,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        result = run_agent_analysis(db, task, settings)
        assert result.get("sql")
        assert result.get("platform", {}).get("data_plane", {}).get("source_type") == "postgres_ro"
        assert result.get("platform", {}).get("skill_id") == "data.bi"
        db.commit()
        print("M3 smoke OK:", ds.id, "sql=", result.get("sql")[:80])
    finally:
        db.close()


if __name__ == "__main__":
    main()
