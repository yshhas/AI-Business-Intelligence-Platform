"""Wave 3 platform MVP smokes: guardrails, MCP, OIDC-off, memory, ACL tables, idempotency, plane protocol."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Dataset, DatasetAcl, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import mcp_tools, oidc_service, workspace_memory  # noqa: E402
from app.services.dataset_service import allowed_tables_for  # noqa: E402
from app.services.task_service import create_task  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def main() -> None:
    # Guardrails
    from agent.guardrails import apply_output_guardrails, redact_text

    assert "[REDACTED_EMAIL]" in redact_text("contact me@example.com now")
    guarded = apply_output_guardrails(
        {"summary": "key sk-abcdefghijklmnopqrstuvwxyz12", "report": {"markdown": "a@b.co"}}
    )
    assert "REDACTED" in guarded["summary"] or "REDACTED" in guarded["report"]["markdown"]
    print("GUARDRAILS_OK")

    # Plane protocol marker
    from agent.data_plane import SUPPORTED_SOURCE_TYPES

    assert "mysql_ro" in SUPPORTED_SOURCE_TYPES
    print("DATA_PLANE_PROTOCOL_OK")

    # OIDC disabled → 404
    get_settings.cache_clear()
    settings = get_settings()
    settings.oidc_enabled = False
    assert oidc_service.oidc_configured(settings) is False
    client = TestClient(app)
    res = client.get("/api/v1/auth/oidc/login")
    assert res.status_code == 404, res.text
    print("OIDC_DISABLED_OK")

    openapi = client.get("/openapi.json").json()
    paths = openapi.get("paths") or {}
    assert any("/mcp/" in p for p in paths), paths
    assert "/api/v1/auth/oidc/login" in paths
    print("OPENAPI_WAVE3_OK")

    db = SessionLocal()
    try:
        email = f"w3_{uuid4().hex[:8]}@example.com"
        user = User(
            email=email,
            password_hash=hash_password("password123"),
            display_name="W3",
        )
        db.add(user)
        db.flush()
        ws = Workspace(name="W3 WS", owner_user_id=user.id)
        db.add(ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
        table = f"ds_{uuid4().hex}"
        ds = Dataset(
            workspace_id=ws.id,
            name="w3",
            source_type="file",
            original_filename="x.csv",
            storage_path="x",
            duckdb_table=table,
            schema_json=[{"name": "region", "type": "VARCHAR"}],
            row_count=1,
            status="ready",
            created_by=user.id,
            source_config_json={},
        )
        db.add(ds)
        db.commit()
        db.refresh(user)
        db.refresh(ws)
        db.refresh(ds)

        # MCP tools + gate (ACL-projected allowlist via dataset_id)
        tools = mcp_tools.list_tools()
        assert any(t["name"] == "sql.gate_validate" for t in tools)
        denied = mcp_tools.invoke_tool(
            db,
            workspace_id=ws.id,
            user_id=user.id,
            tool_name="sql.gate_validate",
            arguments={"sql": f'DROP TABLE "{table}"', "dataset_id": str(ds.id)},
        )
        assert denied["ok"] is False
        print("MCP_GATE_OK")

        # Memory persist + load
        n = workspace_memory.remember_from_link(
            db,
            workspace_id=ws.id,
            dataset_id=ds.id,
            question="按 region 汇总",
            selected_columns=["region"],
        )
        assert n > 0
        syn = workspace_memory.load_synonyms(db, workspace_id=ws.id, dataset_id=ds.id)
        assert any("region" in cols for cols in syn.values())
        db.commit()
        print("WORKSPACE_MEMORY_OK")

        # P1.3 — TTL: expired rows excluded from load; grandfather NULL still loads
        from datetime import UTC, datetime, timedelta

        from app.models import WorkspaceColumnMemory
        from sqlalchemy import func, select

        expired = WorkspaceColumnMemory(
            workspace_id=ws.id,
            dataset_id=ds.id,
            phrase=f"expired_{uuid4().hex[:6]}",
            column_tokens=["region"],
            hit_count=99,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        db.add(expired)
        db.commit()
        syn2 = workspace_memory.load_synonyms(db, workspace_id=ws.id, dataset_id=ds.id)
        assert expired.phrase not in syn2
        print("WORKSPACE_MEMORY_TTL_OK")

        # P1.3 — capacity cap: expire-then-LRU keeps count <= max_rows
        settings.workspace_memory_max_rows = 8
        for i in range(20):
            workspace_memory.remember_from_link(
                db,
                workspace_id=ws.id,
                dataset_id=ds.id,
                question=f"cap phrase unique{i} column",
                selected_columns=[f"col_{i}"],
            )
        db.commit()
        cnt = int(
            db.scalar(
                select(func.count()).select_from(WorkspaceColumnMemory).where(
                    WorkspaceColumnMemory.workspace_id == ws.id
                )
            )
            or 0
        )
        assert cnt <= settings.workspace_memory_max_rows, cnt
        print(f"WORKSPACE_MEMORY_CAP_OK rows={cnt} max={settings.workspace_memory_max_rows}")

        # ACL table projection
        acl = DatasetAcl(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            can_read=True,
            can_run=True,
            tables_json=[table],
        )
        db.add(acl)
        db.commit()
        allowed = allowed_tables_for(ds, db=db, user_id=user.id)
        assert allowed == {table}
        print("ACL_TABLE_PROJECTION_OK")

        # Idempotency + skill_id=data.profile
        settings.skill_data_profile_enabled = True
        from app.services import skill_lifecycle as skills

        skills.sync_from_settings(settings)
        idem_key = f"wave3-idem-{uuid4().hex[:8]}"
        t1 = create_task(
            db,
            workspace_id=ws.id,
            user_id=user.id,
            dataset_id=ds.id,
            question="profile please",
            member_role="owner",
            skill_id="data.profile",
            idempotency_key=idem_key,
        )
        assert t1.skill_id == "data.profile"
        t2 = create_task(
            db,
            workspace_id=ws.id,
            user_id=user.id,
            dataset_id=ds.id,
            question="profile please again",
            member_role="owner",
            skill_id="data.profile",
            idempotency_key=idem_key,
        )
        assert t2.id == t1.id
        print("IDEMPOTENCY_AND_PROFILE_ENQUEUE_OK")
    finally:
        db.close()

    print("WAVE3_PLATFORM_OK")


if __name__ == "__main__":
    main()
