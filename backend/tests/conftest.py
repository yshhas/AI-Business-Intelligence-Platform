"""Pytest configuration for backend unit tests.

No database, no Redis, no FastAPI — pure unit tests for business logic.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

# Ensure backend/ is on sys.path so imports like 'from app.services import ...' work.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Mock redis before any module imports it (queue.py has `import redis`).
sys.modules.setdefault("redis", MagicMock())

# Mock app.core.db to prevent create_engine() call (needs psycopg).
sys.modules.setdefault("app.core.db", MagicMock())

# Mock native DB driver services to prevent cascading import failures.
sys.modules.setdefault("app.services.postgres_ro_service", MagicMock())
sys.modules.setdefault("app.services.duckdb_service", MagicMock())


@pytest.fixture
def mock_db() -> MagicMock:
    """Mock SQLAlchemy Session with common chain-mock patterns.

    Tests can set:
        db.scalars.return_value.all.return_value = [...]
        db.execute.return_value.scalar_one_or_none.return_value = ...
        db.get.return_value = ...
    """
    db = MagicMock(spec=Session)
    return db


def make_task(**overrides):
    """Factory for AnalysisTask with safe defaults.

    Shared across backend test files.
    """
    from app.models.task import AnalysisTask

    kwargs = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "dataset_id": uuid4(),
        "user_id": uuid4(),
        "question": "test",
        "status": "pending",
        "cancel_requested": False,
        "failure_class": None,
        "error_message": None,
        "skill_id": "data.bi",
        "skill_version": "1.0",
        "source_type": None,
        "policy_denied": False,
        "hitl_resume_requested": False,
        "timeout_seconds": 300,
        "llm_total_tokens": None,
        "result_json": None,
        "created_at": None,
        "started_at": None,
        "finished_at": None,
        "require_sql_approval": False,
        "approval_requested_at": None,
        "last_heartbeat_at": None,
    }
    kwargs.update(overrides)
    return AnalysisTask(**kwargs)