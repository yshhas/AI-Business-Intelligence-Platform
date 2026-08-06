"""Pytest configuration for agent tests.

No database, no network, no LLM — pure unit tests for deterministic modules.
Provides shared fixtures to reduce duplication across test files.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from agent.state import AnalysisContext, AnalysisState

# ── Path setup ───────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Shared fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def sample_schema() -> list[dict[str, str]]:
    """Standard 3-column schema used across pipeline / charts / report tests."""
    return [
        {"name": "region", "type": "VARCHAR"},
        {"name": "amount", "type": "DOUBLE"},
        {"name": "order_date", "type": "DATE"},
    ]


@pytest.fixture
def sample_ctx(sample_schema: list[dict[str, str]]) -> AnalysisContext:
    """Default AnalysisContext for pipeline node tests.  Tests may mutate
    the returned instance (it is not frozen)."""
    return AnalysisContext(
        workspace_id=uuid4(),
        dataset_id=uuid4(),
        question="Show sales by region",
        duckdb_table="sales_wide",
        schema=sample_schema,
        default_limit=200,
        max_retries=2,
        execute_select=MagicMock(),
        allow_heuristic_sql=False,
    )


@pytest.fixture
def sample_state() -> AnalysisState:
    """Default AnalysisState for pipeline node tests.  Tests that need
    customisation should copy with `{**sample_state, key: val}`."""
    return {
        "question": "Show sales by region",
        "workspace_id": "ws-1",
        "dataset_id": "ds-1",
        "duckdb_table": "sales_wide",
        "schema": [
            {"name": "region", "type": "VARCHAR"},
            {"name": "amount", "type": "DOUBLE"},
        ],
        "sql_draft": "",
        "sql_final": "",
        "gate_ok": False,
        "gate_error": "",
        "preview": {},
        "summary": "",
        "charts": [],
        "report": None,
        "limitations": [],
        "error": "",
        "status": "running",
        "retry_count": 0,
        "max_retries": 2,
        "default_limit": 200,
        "selected_tables": [],
        "selected_columns": [],
        "link_status": "",
        "link_method": "",
        "link_reason": None,
        "column_count_full": 0,
        "column_count_linked": 0,
        "hitl_plan_only": False,
        "hitl_execute_only": False,
        "repair_history": [],
        "repair_class": None,
        "repair_hint": None,
        "repair_stage": None,
        "allowed_tables": ["sales_wide"],
    }


@pytest.fixture
def make_preview() -> object:
    """Factory returning a preview dict with columns / rows / row_count.
    Usage::

        preview = make_preview(["col1", "col2"], [{"col1": 1, "col2": 2}])
    """

    def _make(columns: list[str], rows: list[dict]) -> dict:
        return {"columns": columns, "rows": rows, "row_count": len(rows)}

    return _make