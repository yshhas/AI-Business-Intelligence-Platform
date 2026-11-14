"""Unit tests for app.services.run_lifecycle — status constants, failure
classification, platform metadata injection, and trace column extraction.

All functions are pure logic — no database, Redis, or FastAPI dependency.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.run_lifecycle import (
    FAILURE_BUDGET,
    FAILURE_CANCELLED,
    FAILURE_CAPACITY,
    FAILURE_CONNECTOR,
    FAILURE_ENQUEUE,
    FAILURE_HITL_REJECTED,
    FAILURE_HITL_SNAPSHOT,
    FAILURE_INTERNAL,
    FAILURE_POLICY,
    FAILURE_RUNTIME_RECLAIMED,
    FAILURE_SKILL,
    FAILURE_TIMEOUT,
    FAILURE_UNKNOWN,
    STATUS_AWAITING_APPROVAL,
    TERMINAL_STATUSES,
    apply_trace_columns,
    attach_run_platform,
    classify_exception,
)


# ── classify_exception ───────────────────────────────────────────────────

class TestClassifyException:
    """Maps exception messages to failure_class strings."""

    def test_policy_rejected_explicit(self):
        """'sql policy rejected' → FAILURE_POLICY."""
        exc = Exception("sql policy rejected: unsafe operation")
        assert classify_exception(exc) == FAILURE_POLICY

    def test_policy_rejected_gate(self):
        """'sql gate rejected' → FAILURE_POLICY."""
        exc = Exception("sql gate rejected")
        assert classify_exception(exc) == FAILURE_POLICY

    def test_policy_forbidden_keyword(self):
        """'forbidden keyword' → FAILURE_POLICY."""
        exc = Exception("forbidden keyword detected (DROP)")
        assert classify_exception(exc) == FAILURE_POLICY

    def test_policy_not_in_allowlist(self):
        """'not in allowlist' → FAILURE_POLICY."""
        exc = Exception("Table 'cte' is not in allowlist ['sales_wide']")
        assert classify_exception(exc) == FAILURE_POLICY

    def test_hitl_snapshot_mismatch(self):
        """'snapshot mismatch' → FAILURE_HITL_SNAPSHOT."""
        exc = Exception("snapshot mismatch: sql_sha256 differs")
        assert classify_exception(exc) == FAILURE_HITL_SNAPSHOT

    def test_hitl_snapshot_sha256(self):
        """'sql_sha256' in message → FAILURE_HITL_SNAPSHOT."""
        exc = Exception("sql_sha256 validation failed")
        assert classify_exception(exc) == FAILURE_HITL_SNAPSHOT

    def test_hitl_snapshot_missing(self):
        """HITL execute-only missing approved SQL → FAILURE_HITL_SNAPSHOT."""
        exc = Exception("hitl execute-only: approved sql snapshot missing")
        assert classify_exception(exc) == FAILURE_HITL_SNAPSHOT

    def test_connector_error(self):
        """'connector error:' prefix → FAILURE_CONNECTOR."""
        exc = Exception("connector error: connection refused")
        assert classify_exception(exc) == FAILURE_CONNECTOR

    def test_connector_error_mid_message(self):
        """'connector error:' anywhere in message → FAILURE_CONNECTOR."""
        exc = Exception("runtime: connector error: timeout")
        assert classify_exception(exc) == FAILURE_CONNECTOR

    def test_unknown_fallback(self):
        """Unrecognized message → FAILURE_SKILL (default fallback)."""
        exc = Exception("something went terribly wrong")
        assert classify_exception(exc) == FAILURE_SKILL

    def test_empty_message(self):
        """Empty exception message → FAILURE_SKILL."""
        exc = Exception("")
        assert classify_exception(exc) == FAILURE_SKILL

    def test_non_exception_subclass(self):
        """Works with any BaseException subclass."""
        exc = ValueError("forbidden keyword: INSERT")
        assert classify_exception(exc) == FAILURE_POLICY

    def test_case_insensitive(self):
        """Message matching is case-insensitive."""
        exc = Exception("SQL POLICY REJECTED: UNSAFE")
        assert classify_exception(exc) == FAILURE_POLICY


# ── attach_run_platform ──────────────────────────────────────────────────

class TestAttachRunPlatform:
    """Injects platform.run metadata into result_json."""

    def test_normal_injection(self):
        """Normal path: platform.run fields added."""
        result = attach_run_platform(
            {"summary": "ok"},
            status="succeeded",
            failure_class=None,
            cancel_requested=False,
            timeout_seconds=300,
            task_id="abc-123",
        )
        run = result["platform"]["run"]
        assert run["run_id"] == "abc-123"
        assert run["status"] == "succeeded"
        assert run["failure_class"] is None
        assert run["cancel_requested"] is False
        assert run["timeout_seconds"] == 300
        assert result["summary"] == "ok"

    def test_cancelled_marks_incomplete(self):
        """Cancelled status → execution.summary.incomplete=True."""
        result = attach_run_platform(
            {"platform": {"execution": {"summary": {"incomplete": False}}}},
            status="cancelled",
            failure_class=FAILURE_CANCELLED,
            cancel_requested=True,
            timeout_seconds=300,
            task_id="abc-123",
        )
        assert result["platform"]["execution"]["summary"]["incomplete"] is True

    def test_timed_out_marks_incomplete(self):
        """timed_out status → execution.summary.incomplete=True."""
        result = attach_run_platform(
            {"platform": {"execution": {"summary": {}}}},
            status="timed_out",
            failure_class=FAILURE_TIMEOUT,
            cancel_requested=False,
            timeout_seconds=300,
            task_id="abc-123",
        )
        assert result["platform"]["execution"]["summary"]["incomplete"] is True

    def test_runtime_reclaimed_marks_incomplete(self):
        """runtime_reclaimed failure_class → execution.summary.incomplete=True."""
        result = attach_run_platform(
            {"platform": {"execution": {"summary": {}}}},
            status="failed",
            failure_class=FAILURE_RUNTIME_RECLAIMED,
            cancel_requested=False,
            timeout_seconds=300,
            task_id="abc-123",
        )
        assert result["platform"]["execution"]["summary"]["incomplete"] is True

    def test_no_execution_in_platform(self):
        """Missing execution key → no crash, incomplete not set."""
        result = attach_run_platform(
            {"platform": {}},
            status="cancelled",
            failure_class=FAILURE_CANCELLED,
            cancel_requested=True,
            timeout_seconds=300,
            task_id="abc-123",
        )
        assert "execution" not in result["platform"]

    def test_none_result_handled(self):
        """None result_json → returns dict with platform."""
        result = attach_run_platform(
            None,
            status="failed",
            failure_class=FAILURE_UNKNOWN,
            cancel_requested=False,
            timeout_seconds=300,
            task_id="abc-123",
        )
        assert result["platform"]["run"]["status"] == "failed"

    def test_preserves_existing_keys(self):
        """Existing keys in result_json are preserved."""
        result = attach_run_platform(
            {"charts": [{"type": "bar"}]},
            status="succeeded",
            failure_class=None,
            cancel_requested=False,
            timeout_seconds=300,
            task_id="abc-123",
        )
        assert result["charts"] == [{"type": "bar"}]


# ── apply_trace_columns ──────────────────────────────────────────────────

class TestApplyTraceColumns:
    """Denormalizes M4 filter columns from platform onto task ORM object."""

    def test_skill_id_extracted(self):
        """skill_id from platform is written to task.skill_id (truncated to 64)."""
        task = MagicMock()
        task.skill_id = None
        task.skill_version = None
        task.source_type = None
        task.policy_denied = False

        apply_trace_columns(
            task,
            {"platform": {"skill_id": "data.bi", "skill_version": "1.0"}},
        )
        assert task.skill_id == "data.bi"
        assert task.skill_version == "1.0"

    def test_skill_id_truncated(self):
        """skill_id longer than 64 chars is truncated."""
        task = MagicMock()
        long_id = "data.bi" + "x" * 60  # > 64 chars
        apply_trace_columns(
            task,
            {"platform": {"skill_id": long_id}},
        )
        assert len(task.skill_id) == 64

    def test_source_type_extracted(self):
        """source_type from data_plane is written to task.source_type."""
        task = MagicMock()
        task.source_type = None
        apply_trace_columns(
            task,
            {"platform": {"data_plane": {"source_type": "file"}}},
        )
        assert task.source_type == "file"

    def test_source_type_truncated(self):
        """source_type longer than 20 chars is truncated."""
        task = MagicMock()
        apply_trace_columns(
            task,
            {"platform": {"data_plane": {"source_type": "postgresql_readonly"}}},
        )
        assert task.source_type == "postgresql_readonly"[:20]

    def test_policy_denied_from_summary(self):
        """policy_deny_count > 0 in execution.summary → policy_denied=True."""
        task = MagicMock()
        task.policy_denied = False
        apply_trace_columns(
            task,
            {"platform": {"execution": {"summary": {"policy_deny_count": 3}}}},
        )
        assert task.policy_denied is True

    def test_policy_denied_from_decisions_fallback(self):
        """When deny_count=0, counts policy_decisions with ok=False."""
        task = MagicMock()
        task.policy_denied = False
        apply_trace_columns(
            task,
            {
                "platform": {
                    "execution": {
                        "summary": {"policy_deny_count": 0},
                        "policy_decisions": [
                            {"ok": True, "policy_id": "a"},
                            {"ok": False, "policy_id": "b"},
                        ],
                    }
                }
            },
        )
        assert task.policy_denied is True

    def test_policy_denied_zero_denies(self):
        """No denied decisions → policy_denied=False."""
        task = MagicMock()
        task.policy_denied = False
        apply_trace_columns(
            task,
            {
                "platform": {
                    "execution": {
                        "summary": {"policy_deny_count": 0},
                        "policy_decisions": [
                            {"ok": True, "policy_id": "a"},
                        ],
                    }
                }
            },
        )
        assert task.policy_denied is False

    def test_empty_result_json(self):
        """Empty result_json → no crash, task fields unchanged."""
        task = MagicMock()
        task.skill_id = None
        apply_trace_columns(task, None)
        assert task.skill_id is None

    def test_missing_platform(self):
        """Missing platform key → no crash."""
        task = MagicMock()
        apply_trace_columns(task, {})
        # No exception = pass

    def test_non_dict_execution(self):
        """execution is not a dict → no crash, policy_denied unchanged."""
        task = MagicMock()
        task.policy_denied = False
        apply_trace_columns(
            task,
            {"platform": {"execution": None}},
        )
        assert task.policy_denied is False


# ── Constants ────────────────────────────────────────────────────────────

class TestConstants:
    """Verify status and failure class constants are correct."""

    def test_terminal_statuses(self):
        """TERMINAL_STATUSES includes all four end states."""
        assert TERMINAL_STATUSES == frozenset({"succeeded", "failed", "cancelled", "timed_out"})

    def test_awaiting_approval_not_terminal(self):
        """awaiting_approval is not a terminal status."""
        assert STATUS_AWAITING_APPROVAL not in TERMINAL_STATUSES

    def test_failure_classes_distinct(self):
        """All failure class constants are distinct."""
        classes = {
            FAILURE_ENQUEUE,
            FAILURE_CAPACITY,
            FAILURE_BUDGET,
            FAILURE_POLICY,
            FAILURE_CONNECTOR,
            FAILURE_SKILL,
            FAILURE_TIMEOUT,
            FAILURE_CANCELLED,
            FAILURE_RUNTIME_RECLAIMED,
            FAILURE_HITL_REJECTED,
            FAILURE_HITL_SNAPSHOT,
            FAILURE_INTERNAL,
            FAILURE_UNKNOWN,
        }
        assert len(classes) == 13