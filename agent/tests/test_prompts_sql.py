"""Unit tests for agent.prompts_sql — repair guidance injection."""

from __future__ import annotations

import pytest

from agent.prompts_sql import build_text_to_sql_prompts


# ── Helpers ──────────────────────────────────────────────────────────────

_ALLOWED = ["sales_wide"]
_TABLE = "sales_wide"
_DIALECT = "DuckDB"
_QUESTION = "Show total sales by region"


# ── _build_repair_guidance ───────────────────────────────────────────────

class TestBuildRepairGuidance:
    """Verify repair guidance is injected when repair_hint present."""

    def test_no_repair_hint(self, sample_schema):
        _, user = build_text_to_sql_prompts(
            dialect=_DIALECT,
            table=_TABLE,
            allowed_tables=_ALLOWED,
            schema=sample_schema,
            question=_QUESTION,
            gate_error="none",
        )
        assert "Repair Guidance" not in user
        assert "Suggested action" not in user

    def test_repair_hint_none(self, sample_schema):
        _, user = build_text_to_sql_prompts(
            dialect=_DIALECT,
            table=_TABLE,
            allowed_tables=_ALLOWED,
            schema=sample_schema,
            question=_QUESTION,
            gate_error="none",
            repair_hint=None,
        )
        assert "Repair Guidance" not in user

    def test_repair_hint_inject_guidance(self, sample_schema):
        _, user = build_text_to_sql_prompts(
            dialect=_DIALECT,
            table=_TABLE,
            allowed_tables=_ALLOWED,
            schema=sample_schema,
            question=_QUESTION,
            gate_error="[policy_allowlist] Table not in allowlist",
            repair_hint={
                "repair_class": "policy_allowlist",
                "action": "Use only allowed tables",
                "is_repairable": True,
            },
        )
        assert "--- Repair Guidance ---" in user
        assert "Error type: policy_allowlist" in user
        assert "Suggested action: Use only allowed tables" in user
        assert "Please generate a corrected SQL" in user
        assert "------------------------" in user

    def test_repair_hint_engine_syntax(self, sample_schema):
        _, user = build_text_to_sql_prompts(
            dialect=_DIALECT,
            table=_TABLE,
            allowed_tables=_ALLOWED,
            schema=sample_schema,
            question=_QUESTION,
            gate_error="[engine_syntax] syntax error",
            repair_hint={
                "repair_class": "engine_syntax",
                "action": "Fix SQL syntax",
                "is_repairable": True,
            },
        )
        assert "Error type: engine_syntax" in user
        assert "Suggested action: Fix SQL syntax" in user

    def test_repair_hint_policy_keyword(self, sample_schema):
        _, user = build_text_to_sql_prompts(
            dialect=_DIALECT,
            table=_TABLE,
            allowed_tables=_ALLOWED,
            schema=sample_schema,
            question=_QUESTION,
            gate_error="[policy_keyword] Forbidden keyword",
            repair_hint={
                "repair_class": "policy_keyword",
                "action": "Remove forbidden DDL/DML",
                "is_repairable": False,
            },
        )
        assert "Error type: policy_keyword" in user
        assert "Remove forbidden DDL/DML" in user

    def test_repair_hint_empty_dict(self, sample_schema):
        """Empty dict should not inject guidance."""
        _, user = build_text_to_sql_prompts(
            dialect=_DIALECT,
            table=_TABLE,
            allowed_tables=_ALLOWED,
            schema=sample_schema,
            question=_QUESTION,
            gate_error="some error",
            repair_hint={},
        )
        assert "Repair Guidance" not in user


# ── No repair_hint preserves original prompt ─────────────────────────────

class TestOriginalPromptPreserved:
    """When no repair_hint, prompt must be identical to pre-Phase2 behavior."""

    def test_prompt_structure_intact(self, sample_schema):
        _, user = build_text_to_sql_prompts(
            dialect=_DIALECT,
            table=_TABLE,
            allowed_tables=_ALLOWED,
            schema=sample_schema,
            question=_QUESTION,
            gate_error="none",
        )
        # Core sections present
        assert "Primary table:" in user
        assert "Allowed tables:" in user
        assert "Columns (primary):" in user
        assert "Previous gate/error (if any):" in user
        assert "Respond with JSON only:" in user
        # No repair leakage
        assert "Repair Guidance" not in user

    def test_gate_error_passed_through(self, sample_schema):
        _, user = build_text_to_sql_prompts(
            dialect=_DIALECT,
            table=_TABLE,
            allowed_tables=_ALLOWED,
            schema=sample_schema,
            question=_QUESTION,
            gate_error="[policy_allowlist] Table not allowed",
        )
        assert "Previous gate/error (if any): [policy_allowlist] Table not allowed" in user

    def test_link_status_partial(self, sample_schema):
        """link_status != 'ok' shows a note."""
        _, user = build_text_to_sql_prompts(
            dialect=_DIALECT,
            table=_TABLE,
            allowed_tables=_ALLOWED,
            schema=sample_schema,
            question=_QUESTION,
            gate_error="none",
            link_status="partial",
        )
        assert "Schema-link status:" in user
        assert "partial" in user

    def test_link_status_ok_suppressed(self, sample_schema):
        """link_status='ok' is suppressed (normal flow)."""
        _, user = build_text_to_sql_prompts(
            dialect=_DIALECT,
            table=_TABLE,
            allowed_tables=_ALLOWED,
            schema=sample_schema,
            question=_QUESTION,
            gate_error="none",
            link_status="ok",
        )
        assert "Schema-link status:" not in user

    def test_link_status_none(self, sample_schema):
        _, user = build_text_to_sql_prompts(
            dialect=_DIALECT,
            table=_TABLE,
            allowed_tables=_ALLOWED,
            schema=sample_schema,
            question=_QUESTION,
            gate_error="none",
            link_status=None,
        )
        assert "Schema-link status:" not in user