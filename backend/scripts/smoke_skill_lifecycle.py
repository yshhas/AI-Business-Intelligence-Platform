"""T-09 smoke: Skill Lifecycle lite — version pin + disable gate (no marketplace)."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import skill_lifecycle as skills  # noqa: E402
from app.services.skill_lifecycle import SkillLifecycleError  # noqa: E402
from app.services.task_service import TaskServiceError, create_task  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.skill_data_bi_enabled = True
    settings.skill_data_bi_version = "1.0.0"

    catalog = skills.catalog(settings)
    bi = next(s for s in catalog if s["skill_id"] == "data.bi")
    assert bi["enabled"] is True
    assert bi["version"] == "1.0.0"
    assert bi["display_name"]
    profile = next(s for s in catalog if s["skill_id"] == "data.profile")
    assert profile["enabled"] is True
    print("SKILL_CATALOG_OK")

    # Disable → enqueue gate
    settings.skill_data_bi_enabled = False
    skills.sync_from_settings(settings)
    try:
        skills.assert_skill_invokable(settings, skill_id="data.bi")
        raise AssertionError("expected disabled skill to raise")
    except SkillLifecycleError as exc:
        assert exc.status_code == 403
    print("SKILL_DISABLE_GATE_OK")

    # Kernel refuses disabled skill
    from agent.kernel.runtime import run as kernel_run
    from agent.kernel.types import RunRequest

    req = RunRequest(
        skill_id="data.bi",
        workspace_id=uuid4(),
        input={"question": "x", "dataset_id": str(uuid4())},
    )
    disabled = kernel_run(req)
    assert disabled.success is False
    assert "disabled" in (disabled.error_message or "").lower()
    assert disabled.skill_version == "1.0.0"
    print("KERNEL_DISABLE_OK")

    # Re-enable + create task pins version
    settings.skill_data_bi_enabled = True
    settings.skill_data_bi_version = "1.0.0"
    skills.sync_from_settings(settings)

    db = SessionLocal()
    try:
        email = f"skl_{uuid4().hex[:8]}@example.com"
        user = User(
            email=email,
            password_hash=hash_password("password123"),
            display_name="SkillLife",
        )
        db.add(user)
        db.flush()
        ws = Workspace(name="SKL WS", owner_user_id=user.id)
        db.add(ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
        ds = Dataset(
            workspace_id=ws.id,
            name="skl",
            source_type="file",
            original_filename="x.csv",
            storage_path="x",
            duckdb_table=f"ds_{uuid4().hex}",
            schema_json=[{"name": "a", "type": "INTEGER"}],
            row_count=0,
            status="ready",
            created_by=user.id,
        )
        db.add(ds)
        db.commit()
        db.refresh(user)
        db.refresh(ws)
        db.refresh(ds)

        task = create_task(
            db,
            workspace_id=ws.id,
            user_id=user.id,
            dataset_id=ds.id,
            question="pin version",
            member_role="owner",
        )
        assert task.skill_id == "data.bi"
        assert task.skill_version == "1.0.0"

        settings.skill_data_bi_enabled = False
        skills.sync_from_settings(settings)
        try:
            create_task(
                db,
                workspace_id=ws.id,
                user_id=user.id,
                dataset_id=ds.id,
                question="should fail",
                member_role="owner",
            )
            raise AssertionError("create_task should fail when disabled")
        except TaskServiceError as exc:
            assert exc.status_code == 403
        print("RUN_PIN_AND_ENQUEUE_DENY_OK")
    finally:
        # restore for other smokes in same process
        settings.skill_data_bi_enabled = True
        skills.sync_from_settings(settings)
        db.close()

    print("SKILL_LIFECYCLE_T09_OK")


if __name__ == "__main__":
    main()
