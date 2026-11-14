"""Unit tests for app.workers.analysis_worker.

Covers: pure HITL functions, state machine transitions (_mark_cancelled,
        _mark_timed_out, _mark_awaiting_approval), and the core task lifecycle
        orchestrator (process_task).

No database, no Redis, no agent runtime — pure unit tests for business logic.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.models.task import AnalysisTask
from app.workers.agent_runtime import AgentAnalysisError
from app.workers.analysis_worker import (
    _Cancelled,
    _TimedOut,
    _hitl_platform,
    _is_hitl_execute_phase,
    _list_hitl_resume_recovery_ids,
    _mark_awaiting_approval,
    _mark_cancelled,
    _mark_hitl_snapshot_failed,
    _mark_timed_out,
    _next_step_no,
    _should_park_hitl,
    process_hitl_resume,
    process_task,
)


def _make_task(**overrides):
    """Factory for AnalysisTask with safe defaults."""
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


# ═══════════════════════════════════════════════════════════════════════════
# _hitl_platform — pure function
# ═══════════════════════════════════════════════════════════════════════════

class TestHitlPlatform:
    """Extract HITL dict from task.result_json.platform."""

    def test_result_json_is_none(self):
        """None result_json → {}."""
        task = _make_task(result_json=None)
        assert _hitl_platform(task) == {}

    def test_result_json_has_no_platform(self):
        """result_json without 'platform' key → {}."""
        task = _make_task(result_json={"sql": "SELECT 1", "chart": {}})
        assert _hitl_platform(task) == {}

    def test_platform_has_no_hitl(self):
        """platform dict without 'hitl' key → {}."""
        task = _make_task(
            result_json={
                "platform": {"skill_id": "data.bi", "execution": {}},
            }
        )
        assert _hitl_platform(task) == {}

    def test_result_json_is_not_dict(self):
        """result_json is a list → {}."""
        task = _make_task(result_json=[1, 2, 3])
        assert _hitl_platform(task) == {}

    def test_full_hitl_dict(self):
        """result_json.platform.hitl exists → return hitl dict."""
        task = _make_task(
            result_json={
                "platform": {
                    "hitl": {
                        "required": True,
                        "phase": "execute",
                        "decision": "approved",
                    }
                }
            }
        )
        assert _hitl_platform(task) == {
            "required": True,
            "phase": "execute",
            "decision": "approved",
        }

    def test_hitl_is_not_dict(self):
        """platform.hitl is a string → {}."""
        task = _make_task(
            result_json={"platform": {"hitl": "not-a-dict"}}
        )
        assert _hitl_platform(task) == {}


# ═══════════════════════════════════════════════════════════════════════════
# _is_hitl_execute_phase — pure function
# ═══════════════════════════════════════════════════════════════════════════

class TestIsHitlExecutePhase:
    """Check if task is in HITL execute phase (both phase=execute and decision=approved)."""

    def test_execute_and_approved(self):
        """phase=execute + decision=approved → True."""
        task = _make_task(
            result_json={
                "platform": {
                    "hitl": {"phase": "execute", "decision": "approved"}
                }
            }
        )
        assert _is_hitl_execute_phase(task) is True

    def test_execute_but_not_approved(self):
        """phase=execute + decision=rejected → False."""
        task = _make_task(
            result_json={
                "platform": {
                    "hitl": {"phase": "execute", "decision": "rejected"}
                }
            }
        )
        assert _is_hitl_execute_phase(task) is False

    def test_approved_but_not_execute_phase(self):
        """phase=awaiting + decision=approved → False."""
        task = _make_task(
            result_json={
                "platform": {
                    "hitl": {"phase": "awaiting", "decision": "approved"}
                }
            }
        )
        assert _is_hitl_execute_phase(task) is False

    def test_no_hitl_at_all(self):
        """No hitl dict → False."""
        task = _make_task(result_json=None)
        assert _is_hitl_execute_phase(task) is False


# ═══════════════════════════════════════════════════════════════════════════
# _should_park_hitl — pure function
# ═══════════════════════════════════════════════════════════════════════════

class TestShouldParkHitl:
    """Decide whether to park task for HITL approval after plan."""

    @staticmethod
    def _settings(**overrides) -> MagicMock:
        s = MagicMock()
        s.hitl_sql_approval_enabled = True
        for k, v in overrides.items():
            setattr(s, k, v)
        return s

    def test_all_conditions_met(self):
        """enabled=True + require=True + skill=data.bi → True."""
        task = _make_task(require_sql_approval=True, skill_id="data.bi")
        settings = self._settings()
        assert _should_park_hitl(task, settings) is True

    def test_hitl_disabled(self):
        """hitl_sql_approval_enabled=False → False."""
        task = _make_task(require_sql_approval=True, skill_id="data.bi")
        settings = self._settings(hitl_sql_approval_enabled=False)
        assert _should_park_hitl(task, settings) is False

    def test_require_sql_approval_false(self):
        """require_sql_approval=False → False."""
        task = _make_task(require_sql_approval=False, skill_id="data.bi")
        settings = self._settings()
        assert _should_park_hitl(task, settings) is False

    def test_skill_not_data_bi(self):
        """skill_id='custom.report' → False."""
        task = _make_task(require_sql_approval=True, skill_id="custom.report")
        settings = self._settings()
        assert _should_park_hitl(task, settings) is False

    def test_is_execute_phase_returns_false(self):
        """Already in execute phase → False (never re-park)."""
        task = _make_task(
            require_sql_approval=True,
            skill_id="data.bi",
            result_json={
                "platform": {
                    "hitl": {"phase": "execute", "decision": "approved"}
                }
            },
        )
        settings = self._settings()
        assert _should_park_hitl(task, settings) is False

    def test_skill_id_none_defaults_to_data_bi(self):
        """skill_id=None → defaults to 'data.bi' → True."""
        task = _make_task(require_sql_approval=True, skill_id=None)
        settings = self._settings()
        assert _should_park_hitl(task, settings) is True

    def test_skill_id_whitespace_defaults_to_data_bi(self):
        """skill_id='  ' → defaults to 'data.bi' → True."""
        task = _make_task(require_sql_approval=True, skill_id="  ")
        settings = self._settings()
        assert _should_park_hitl(task, settings) is True


# ═══════════════════════════════════════════════════════════════════════════
# _next_step_no — simple DB query
# ═══════════════════════════════════════════════════════════════════════════

class TestNextStepNo:
    """Compute next AgentRunStep step_no from existing steps."""

    def test_no_existing_steps(self, mock_db):
        """No steps → returns 1."""
        mock_db.scalar.return_value = 0
        tid = uuid4()

        result = _next_step_no(mock_db, tid)

        assert result == 1
        mock_db.scalar.assert_called_once()

    def test_has_existing_steps(self, mock_db):
        """Max step_no=5 → returns 6."""
        mock_db.scalar.return_value = 5
        tid = uuid4()

        result = _next_step_no(mock_db, tid)

        assert result == 6
        mock_db.scalar.assert_called_once()

    def test_returns_none_coerced_to_zero(self, mock_db):
        """scalar returns None → 0 + 1 = 1."""
        mock_db.scalar.return_value = None
        tid = uuid4()

        result = _next_step_no(mock_db, tid)

        assert result == 1


# ═══════════════════════════════════════════════════════════════════════════
# _list_hitl_resume_recovery_ids — simple DB query
# ═══════════════════════════════════════════════════════════════════════════

class TestListHitlResumeRecoveryIds:
    """Recover HITL resume task IDs from DB (Worker restart)."""

    def test_no_matching_rows(self, mock_db):
        """No awaiting+resume tasks → []."""
        mock_db.scalars.return_value.all.return_value = []

        result = _list_hitl_resume_recovery_ids(mock_db)

        assert result == []
        mock_db.scalars.assert_called_once()

    def test_has_matching_rows(self, mock_db):
        """Returns list of UUIDs for awaiting+resume tasks."""
        tid1 = uuid4()
        tid2 = uuid4()
        mock_db.scalars.return_value.all.return_value = [tid1, tid2]

        result = _list_hitl_resume_recovery_ids(mock_db)

        assert result == [tid1, tid2]
        mock_db.scalars.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Batch 2: _mark_cancelled / _mark_timed_out / _mark_awaiting_approval
# ═══════════════════════════════════════════════════════════════════════════


def _setup_mark_mocks(mock_db):
    """Start all patches for _mark_* state machine tests. Returns (mocks, stop_fn)."""
    _patchers = []
    _mocks = {}

    def _start(name: str, target: str, **kw: object) -> MagicMock:
        p = patch(target, **kw)
        _patchers.append(p)
        m = p.start()
        _mocks[name] = m
        return m

    _start("attach_run_platform",
           "app.workers.analysis_worker.rl.attach_run_platform",
           side_effect=lambda base, **kw: {
               **base,
               "_platform": {**base.get("platform", {}), **kw},
           })
    _start("apply_trace_columns",
           "app.workers.analysis_worker.rl.apply_trace_columns",
           return_value=None)
    _start("seal_result_json",
           "app.workers.analysis_worker._seal_result_json",
           return_value=None)
    _start("finalize_tokens",
           "app.workers.analysis_worker._finalize_tokens",
           return_value=None)
    _start("observe_terminal",
           "app.workers.analysis_worker._observe_terminal",
           return_value=None)
    _start("materialize_artifacts",
           "app.workers.analysis_worker._materialize_artifacts",
           return_value=None)
    _start("slim_for_persist",
           "app.workers.analysis_worker.result_payload.slim_for_persist",
           side_effect=lambda x: x)
    _start("log_run",
           "app.workers.analysis_worker.log_run",
           return_value=None)

    def _stop() -> None:
        for p in reversed(_patchers):
            p.stop()

    return _mocks, _stop


# ── _mark_cancelled ─────────────────────────────────────────────────────

class TestMarkCancelled:
    """_mark_cancelled: running → cancelled terminal state machine."""

    def test_from_running(self, mock_db):
        """running → cancelled: all fields set correctly."""
        task = _make_task(
            status="running",
            result_json={"sql": "SELECT 1", "chart": {"type": "bar"}},
            timeout_seconds=120,
        )
        mocks, stop = _setup_mark_mocks(mock_db)

        try:
            _mark_cancelled(mock_db, task, "Run cancelled by user")
        finally:
            stop()

        assert task.status == "cancelled"
        assert task.cancel_requested is True
        assert task.failure_class == "cancelled"
        assert task.error_message == "Run cancelled by user"
        assert task.finished_at is not None

        # result_json updated via attach_run_platform
        assert isinstance(task.result_json, dict)
        assert "_platform" in task.result_json
        assert task.result_json["_platform"]["status"] == "cancelled"
        assert task.result_json["_platform"]["cancel_requested"] is True
        # CANCEL_LIMITATIONS appended
        assert "limitations" in task.result_json
        assert len(task.result_json["limitations"]) > 0

        # External calls
        mocks["attach_run_platform"].assert_called_once()
        mocks["seal_result_json"].assert_called_once_with(mock_db, task)
        mocks["finalize_tokens"].assert_called_once_with(mock_db, task)
        mocks["observe_terminal"].assert_called_once_with(task)
        mocks["log_run"].assert_called_once()
        mock_db.add.assert_called_with(task)
        mock_db.commit.assert_called()

    def test_already_cancelled_noop(self, mock_db):
        """Already cancelled → return immediately, no external calls."""
        task = _make_task(status="cancelled", cancel_requested=True)
        mocks, stop = _setup_mark_mocks(mock_db)

        try:
            _mark_cancelled(mock_db, task, "Should be ignored")
        finally:
            stop()

        # All external functions should NOT be called
        mocks["attach_run_platform"].assert_not_called()
        mocks["seal_result_json"].assert_not_called()
        mocks["finalize_tokens"].assert_not_called()
        mocks["observe_terminal"].assert_not_called()
        mocks["log_run"].assert_not_called()
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_limitations_appended(self, mock_db):
        """CANCEL_LIMITATIONS appended to result_json.limitations."""
        task = _make_task(
            status="running",
            result_json={"sql": "SELECT 1", "limitations": []},
        )
        mocks, stop = _setup_mark_mocks(mock_db)

        try:
            _mark_cancelled(mock_db, task, "cancelled")
        finally:
            stop()

        assert "limitations" in task.result_json
        # At least one cancellation limitation item
        assert any("cancel" in item.lower() for item in task.result_json["limitations"])

    def test_error_message_preserved(self, mock_db):
        """error_message set to the message parameter."""
        task = _make_task(status="running")
        mocks, stop = _setup_mark_mocks(mock_db)

        try:
            _mark_cancelled(mock_db, task, "Custom cancel reason: timeout")
        finally:
            stop()

        assert task.error_message == "Custom cancel reason: timeout"

    def test_original_data_preserved_in_result_json(self, mock_db):
        """Original result_json data (sql, chart) preserved after cancel."""
        task = _make_task(
            status="running",
            result_json={"sql": "SELECT 1", "chart": {"type": "bar"}},
        )
        mocks, stop = _setup_mark_mocks(mock_db)

        try:
            _mark_cancelled(mock_db, task, "cancelled")
        finally:
            stop()

        assert task.result_json["sql"] == "SELECT 1"
        assert task.result_json["chart"] == {"type": "bar"}


# ── _mark_timed_out ──────────────────────────────────────────────────────

class TestMarkTimedOut:
    """_mark_timed_out: running → timed_out terminal state machine."""

    def test_from_running(self, mock_db):
        """running → timed_out: all fields set correctly."""
        task = _make_task(
            status="running",
            result_json={"sql": "SELECT 1"},
            timeout_seconds=120,
        )
        mocks, stop = _setup_mark_mocks(mock_db)

        try:
            _mark_timed_out(mock_db, task, timeout=120)
        finally:
            stop()

        assert task.status == "timed_out"
        assert task.failure_class == "timeout"
        assert task.error_message == "Run exceeded timeout of 120s"
        assert task.finished_at is not None

        # result_json updated
        assert isinstance(task.result_json, dict)
        assert "_platform" in task.result_json
        assert task.result_json["_platform"]["status"] == "timed_out"
        assert "limitations" in task.result_json

        # External calls
        mocks["attach_run_platform"].assert_called_once()
        mocks["seal_result_json"].assert_called_once_with(mock_db, task)
        mocks["finalize_tokens"].assert_called_once_with(mock_db, task)
        mocks["observe_terminal"].assert_called_once_with(task)
        mocks["log_run"].assert_called_once()
        mock_db.add.assert_called_with(task)
        mock_db.commit.assert_called()

    def test_already_terminal_noop(self, mock_db):
        """Already terminal (succeeded) → return immediately."""
        task = _make_task(status="succeeded", finished_at="2024-01-01T00:00:00")
        mocks, stop = _setup_mark_mocks(mock_db)

        try:
            _mark_timed_out(mock_db, task, timeout=120)
        finally:
            stop()

        # No external calls
        mocks["attach_run_platform"].assert_not_called()
        mocks["seal_result_json"].assert_not_called()
        mocks["finalize_tokens"].assert_not_called()
        mocks["observe_terminal"].assert_not_called()
        mocks["log_run"].assert_not_called()
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_timeout_message_format(self, mock_db):
        """error_message includes timeout value."""
        task = _make_task(status="running")
        mocks, stop = _setup_mark_mocks(mock_db)

        try:
            _mark_timed_out(mock_db, task, timeout=300)
        finally:
            stop()

        assert task.error_message == "Run exceeded timeout of 300s"

    def test_limitations_appended(self, mock_db):
        """TIMEOUT_LIMITATIONS appended to result_json.limitations."""
        task = _make_task(
            status="running",
            result_json={"sql": "SELECT 1", "limitations": []},
        )
        mocks, stop = _setup_mark_mocks(mock_db)

        try:
            _mark_timed_out(mock_db, task, timeout=120)
        finally:
            stop()

        assert "limitations" in task.result_json
        assert any("timed" in item.lower() for item in task.result_json["limitations"])


# ── _mark_awaiting_approval ──────────────────────────────────────────────

def _setup_awaiting_mocks(mock_db):
    """Start patches for _mark_awaiting_approval. Returns (mocks, stop_fn)."""
    _patchers = []
    _mocks = {}

    def _start(name: str, target: str, **kw: object) -> MagicMock:
        p = patch(target, **kw)
        _patchers.append(p)
        m = p.start()
        _mocks[name] = m
        return m

    _start("attach_snapshot_on_park",
           "agent.hitl_snapshot.attach_snapshot_on_park",
           side_effect=lambda rj: rj or {})
    _start("attach_run_platform",
           "app.workers.analysis_worker.rl.attach_run_platform",
           side_effect=lambda base, **kw: {
               **base,
               "_platform": {**base.get("platform", {}), **kw},
           })
    _start("apply_trace_columns",
           "app.workers.analysis_worker.rl.apply_trace_columns",
           return_value=None)
    _start("log_run",
           "app.workers.analysis_worker.log_run",
           return_value=None)

    def _stop() -> None:
        for p in reversed(_patchers):
            p.stop()

    return _mocks, _stop


class TestMarkAwaitingApproval:
    """_mark_awaiting_approval: running → awaiting_approval (HITL park)."""

    def test_from_running(self, mock_db):
        """running → awaiting_approval: status and approval_requested_at set."""
        task = _make_task(
            status="running",
            result_json={"sql": "SELECT 1", "chart": {"type": "bar"}},
        )
        mocks, stop = _setup_awaiting_mocks(mock_db)

        try:
            _mark_awaiting_approval(mock_db, task, None)
        finally:
            stop()

        assert task.status == "awaiting_approval"
        assert task.approval_requested_at is not None
        assert task.failure_class is None
        assert task.error_message is None
        assert task.finished_at is None

        # result_json updated
        assert isinstance(task.result_json, dict)
        assert "_platform" in task.result_json
        assert task.result_json["_platform"]["status"] == "awaiting_approval"

        # External calls
        mocks["attach_snapshot_on_park"].assert_called_once()
        mocks["attach_run_platform"].assert_called_once()
        mocks["apply_trace_columns"].assert_called_once_with(task, task.result_json)
        mocks["log_run"].assert_called_once()
        mock_db.add.assert_called_with(task)
        mock_db.commit.assert_called()

    def test_hitl_metadata_written(self, mock_db):
        """platform.hitl has phase='awaiting' and required=True."""
        task = _make_task(
            status="running",
            result_json={"sql": "SELECT 1", "platform": {"hitl": {"phase": "plan"}}},
        )
        mocks, stop = _setup_awaiting_mocks(mock_db)

        try:
            _mark_awaiting_approval(mock_db, task, None)
        finally:
            stop()

        assert "_platform" in task.result_json
        assert "hitl" in task.result_json["_platform"]
        assert task.result_json["_platform"]["hitl"]["phase"] == "awaiting"
        assert task.result_json["_platform"]["hitl"]["required"] is True

    def test_clears_terminal_fields(self, mock_db):
        """Clears failure_class, error_message, finished_at from previous terminal state."""
        task = _make_task(
            status="failed",
            failure_class="error",
            error_message="Something went wrong",
            finished_at="2024-01-01T00:00:00",
        )
        mocks, stop = _setup_awaiting_mocks(mock_db)

        try:
            _mark_awaiting_approval(mock_db, task, None)
        finally:
            stop()

        assert task.failure_class is None
        assert task.error_message is None
        assert task.finished_at is None

    def test_attach_snapshot_called_with_result_json(self, mock_db):
        """attach_snapshot_on_park receives the result_json dict."""
        task = _make_task(
            status="running",
            result_json={"sql": "SELECT 1", "chart": {"type": "bar"}},
        )
        mocks, stop = _setup_awaiting_mocks(mock_db)

        try:
            _mark_awaiting_approval(mock_db, task, None)
        finally:
            stop()

        mocks["attach_snapshot_on_park"].assert_called_once_with(None)

    def test_null_result_json_defaults_to_empty(self, mock_db):
        """result_json=None → uses empty dict, no crash."""
        task = _make_task(status="running", result_json=None)
        mocks, stop = _setup_awaiting_mocks(mock_db)

        try:
            _mark_awaiting_approval(mock_db, task, None)
        finally:
            stop()

        assert task.status == "awaiting_approval"
        assert isinstance(task.result_json, dict)
        assert "_platform" in task.result_json


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3.1: process_task — core task lifecycle orchestrator
# ═══════════════════════════════════════════════════════════════════════════


def _setup_process_mocks(mock_db):
    """Start all patches for process_task. Returns (mocks, stop_fn).

    Mocks all external dependencies so process_task can exercise its
    internal state machine without touching real DB / Redis / Agent.
    """
    _patchers = []
    _mocks = {}

    def _start(name: str, target: str, **kw: object) -> MagicMock:
        p = patch(target, **kw)
        _patchers.append(p)
        m = p.start()
        _mocks[name] = m
        return m

    # DB session — return our controlled mock_db
    _start("SessionLocal", "app.workers.analysis_worker.SessionLocal",
           return_value=mock_db)

    # Settings
    _settings = MagicMock()
    _settings.analysis_runtime = "mock"
    _settings.run_timeout_seconds = 120
    _settings.run_max_in_flight = 10
    _settings.analysis_queue_max_depth = 100
    _settings.run_heartbeat_interval_seconds = 0
    _settings.hitl_sql_approval_enabled = True
    _start("get_settings", "app.workers.analysis_worker.get_settings",
           return_value=_settings)

    # Runtime essentials
    _start("rt_reclaim", "app.workers.analysis_worker.rt.reclaim_stale_running")
    _start("rt_expire", "app.workers.analysis_worker.rt.expire_awaiting_approval")
    _start("rt_claim", "app.workers.analysis_worker.rt.claim_allowed",
           return_value=True)

    # Queue
    _start("requeue_task", "app.workers.analysis_worker.task_queue.requeue_task")

    # Internal state machine functions (tested separately)
    _start("mark_cancelled", "app.workers.analysis_worker._mark_cancelled")
    _start("mark_timed_out", "app.workers.analysis_worker._mark_timed_out")
    _start("mark_awaiting", "app.workers.analysis_worker._mark_awaiting_approval")
    _start("mark_snapshot", "app.workers.analysis_worker._mark_hitl_snapshot_failed")
    _start("run_with_timeout", "app.workers.analysis_worker._run_with_timeout")
    _start("is_hitl_execute", "app.workers.analysis_worker._is_hitl_execute_phase",
           return_value=False)
    _start("verify_snapshot", "app.workers.analysis_worker._verify_hitl_sql_snapshot")
    _start("should_park", "app.workers.analysis_worker._should_park_hitl",
           return_value=False)

    # Seal / finalize / metrics / logging
    _start("seal", "app.workers.analysis_worker._seal_result_json")
    _start("finalize", "app.workers.analysis_worker._finalize_tokens")
    _start("observe", "app.workers.analysis_worker._observe_terminal")
    _start("log_run", "app.workers.analysis_worker.log_run")

    # run_lifecycle
    _start("rl_attach", "app.workers.analysis_worker.rl.attach_run_platform",
           side_effect=lambda base, **kw: {**base, "_platform": kw})
    _start("rl_apply", "app.workers.analysis_worker.rl.apply_trace_columns")
    _start("rl_classify", "app.workers.analysis_worker.rl.classify_exception",
           return_value="agent_error")

    def _stop() -> None:
        for p in reversed(_patchers):
            p.stop()

    return _mocks, _stop


class TestProcessTask:
    """process_task: core task lifecycle orchestrator.

    Covers: task_not_found, already_terminal, pending_cancel_requested,
            cancelled_during_execution, timed_out_during_execution,
            AgentAnalysisError, HITL park, normal_success.
    """

    def test_unsupported_runtime(self, mock_db):
        """Unsupported runtime → RuntimeError."""
        mocks, stop = _setup_process_mocks(mock_db)
        mocks["get_settings"].return_value.analysis_runtime = "invalid"
        try:
            with pytest.raises(RuntimeError, match="Unsupported ANALYSIS_RUNTIME"):
                process_task(uuid4())
        finally:
            stop()

    def test_task_not_found(self, mock_db):
        """Task not in DB → return silently."""
        mock_db.get.return_value = None
        mocks, stop = _setup_process_mocks(mock_db)

        try:
            process_task(uuid4())
        finally:
            stop()

        # No state machine calls
        mocks["mark_cancelled"].assert_not_called()
        mocks["mark_timed_out"].assert_not_called()
        mocks["mark_awaiting"].assert_not_called()
        mocks["mark_snapshot"].assert_not_called()
        mocks["run_with_timeout"].assert_not_called()

    def test_already_terminal(self, mock_db):
        """Already terminal → return silently."""
        task = _make_task(status="succeeded", finished_at="2024-01-01T00:00:00")
        mock_db.get.return_value = task
        mocks, stop = _setup_process_mocks(mock_db)

        try:
            process_task(task.id)
        finally:
            stop()

        mocks["run_with_timeout"].assert_not_called()
        mocks["mark_cancelled"].assert_not_called()

    def test_pending_cancel_requested(self, mock_db):
        """pending + cancel_requested → _mark_cancelled called."""
        task = _make_task(status="pending", cancel_requested=True)
        mock_db.get.return_value = task
        mocks, stop = _setup_process_mocks(mock_db)

        try:
            process_task(task.id)
        finally:
            stop()

        mocks["mark_cancelled"].assert_called_once_with(
            mock_db, task, "Run cancelled before start"
        )
        mocks["run_with_timeout"].assert_not_called()

    def test_running_cancel_requested(self, mock_db):
        """running + cancel_requested → _mark_cancelled called."""
        task = _make_task(status="running", cancel_requested=True)
        mock_db.get.return_value = task
        mocks, stop = _setup_process_mocks(mock_db)

        try:
            process_task(task.id)
        finally:
            stop()

        mocks["mark_cancelled"].assert_called_once_with(
            mock_db, task, "Run cancelled"
        )

    def test_cancelled_during_execution(self, mock_db):
        """_Cancelled raised → _mark_cancelled called with execution message."""
        task = _make_task(status="running")
        mock_db.get.return_value = task
        mocks, stop = _setup_process_mocks(mock_db)
        mocks["run_with_timeout"].side_effect = _Cancelled()

        try:
            process_task(task.id)
        finally:
            stop()

        mocks["mark_cancelled"].assert_called_once_with(
            mock_db, task, "Run cancelled during execution"
        )
        mocks["mark_timed_out"].assert_not_called()

    def test_timed_out_during_execution(self, mock_db):
        """_TimedOut raised → _mark_timed_out called with timeout value."""
        task = _make_task(status="running", timeout_seconds=120)
        mock_db.get.return_value = task
        mocks, stop = _setup_process_mocks(mock_db)
        mocks["run_with_timeout"].side_effect = _TimedOut()

        try:
            process_task(task.id)
        finally:
            stop()

        mocks["mark_timed_out"].assert_called_once_with(mock_db, task, 120)
        mocks["mark_cancelled"].assert_not_called()

    def test_agent_analysis_error(self, mock_db):
        """AgentAnalysisError → task set to failed, seal/finalize/observe called."""
        task = _make_task(status="running")
        mock_db.get.return_value = task
        mocks, stop = _setup_process_mocks(mock_db)
        mocks["run_with_timeout"].side_effect = AgentAnalysisError(
            "Skill execution failed", result_json={"sql": "SELECT 1"}
        )

        try:
            process_task(task.id)
        finally:
            stop()

        mocks["seal"].assert_called_once_with(mock_db, task)
        mocks["finalize"].assert_called_once_with(mock_db, task)
        mocks["observe"].assert_called_once_with(task)
        mocks["log_run"].assert_called_once()
        mocks["rl_classify"].assert_called_once()

    def test_hitl_park_after_success(self, mock_db):
        """_should_park_hitl returns True → _mark_awaiting_approval called."""
        task = _make_task(status="running")
        mock_db.get.return_value = task
        mocks, stop = _setup_process_mocks(mock_db)
        mocks["run_with_timeout"].return_value = {"sql": "SELECT 1"}
        mocks["should_park"].return_value = True

        try:
            process_task(task.id)
        finally:
            stop()

        mocks["mark_awaiting"].assert_called_once_with(
            mock_db, task, {"sql": "SELECT 1"}
        )

    def test_normal_success(self, mock_db):
        """Normal run → succeeded: seal, finalize, observe, log_run called."""
        task = _make_task(status="running")
        mock_db.get.return_value = task
        mocks, stop = _setup_process_mocks(mock_db)
        mocks["run_with_timeout"].return_value = {"sql": "SELECT 1", "chart": {"type": "bar"}}

        try:
            process_task(task.id)
        finally:
            stop()

        mocks["seal"].assert_called_once_with(mock_db, task)
        mocks["finalize"].assert_called_once_with(mock_db, task)
        mocks["observe"].assert_called_once_with(task)
        mocks["log_run"].assert_called_once()
        mocks["rl_attach"].assert_called_once()

    def test_pending_cas_lost(self, mock_db):
        """pending CAS rowcount=0 (concurrent claim) → defer, no agent execution."""
        task = _make_task(status="pending")
        mock_db.get.return_value = task
        mock_db.execute.return_value.rowcount = 0  # Another worker claimed first
        mocks, stop = _setup_process_mocks(mock_db)

        try:
            process_task(task.id)
        finally:
            stop()

        # CAS lost → no agent execution, no state machine calls
        mocks["run_with_timeout"].assert_not_called()
        mocks["mark_cancelled"].assert_not_called()
        mocks["mark_timed_out"].assert_not_called()
        mocks["mark_awaiting"].assert_not_called()
        # Not requeued (already claimed by another worker)
        mocks["requeue_task"].assert_not_called()
        # db.refresh called to sync state after CAS loss
        mock_db.refresh.assert_called_once_with(task)

    def test_success_discard_when_already_terminal(self, mock_db):
        """Agent succeeds but task is terminal after run → discard, no seal."""
        task_running = _make_task(status="running")
        task_terminal = _make_task(status="cancelled", finished_at="2024-01-01T00:00:00")
        # First get: running task; second get (after run): already terminal
        mock_db.get.side_effect = [task_running, task_terminal]
        mocks, stop = _setup_process_mocks(mock_db)
        mocks["run_with_timeout"].return_value = {"sql": "SELECT 1"}

        try:
            process_task(task_running.id)
        finally:
            stop()

        # Success path should NOT write to DB
        mocks["seal"].assert_not_called()
        mocks["finalize"].assert_not_called()
        mocks["observe"].assert_not_called()
        mocks["rl_attach"].assert_not_called()

    def test_success_marked_cancelled_when_cancel_requested(self, mock_db):
        """Agent succeeds but cancel_requested=True → _mark_cancelled, preserve result."""
        task = _make_task(status="running", cancel_requested=True)
        mock_db.get.return_value = task
        mocks, stop = _setup_process_mocks(mock_db)
        mocks["run_with_timeout"].return_value = {"sql": "SELECT 1", "chart": {"type": "bar"}}

        try:
            process_task(task.id)
        finally:
            stop()

        # Cancel wins → _mark_cancelled called, not succeeded
        mocks["mark_cancelled"].assert_called_once_with(
            mock_db, task, "Run cancelled"
        )
        mocks["seal"].assert_not_called()
        mocks["finalize"].assert_not_called()
        mocks["observe"].assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3.2: process_hitl_resume — HITL H2 CAS recovery
# ═══════════════════════════════════════════════════════════════════════════


def _setup_hitl_resume_mocks(mock_db):
    """Start patches for process_hitl_resume. Returns (mocks, stop_fn).

    Extends _setup_process_mocks with process_task mock.
    """
    _patchers = []
    _mocks = {}

    def _start(name: str, target: str, **kw: object) -> MagicMock:
        p = patch(target, **kw)
        _patchers.append(p)
        m = p.start()
        _mocks[name] = m
        return m

    # DB session
    _start("SessionLocal", "app.workers.analysis_worker.SessionLocal",
           return_value=mock_db)

    # Settings
    _settings = MagicMock()
    _settings.analysis_runtime = "mock"
    _settings.run_timeout_seconds = 120
    _settings.run_max_in_flight = 10
    _settings.analysis_queue_max_depth = 100
    _settings.run_heartbeat_interval_seconds = 0
    _settings.hitl_sql_approval_enabled = True
    _start("get_settings", "app.workers.analysis_worker.get_settings",
           return_value=_settings)

    # Runtime essentials
    _start("rt_reclaim", "app.workers.analysis_worker.rt.reclaim_stale_running")
    _start("rt_expire", "app.workers.analysis_worker.rt.expire_awaiting_approval")

    # run_lifecycle
    _start("rl_attach", "app.workers.analysis_worker.rl.attach_run_platform",
           side_effect=lambda base, **kw: {**base, "_platform": kw})
    _start("rl_apply", "app.workers.analysis_worker.rl.apply_trace_columns")

    # Logging
    _start("log_run", "app.workers.analysis_worker.log_run")

    # process_task — called after CAS win
    _start("process_task", "app.workers.analysis_worker.process_task")

    def _stop() -> None:
        for p in reversed(_patchers):
            p.stop()

    return _mocks, _stop


class TestProcessHitlResume:
    """process_hitl_resume: HITL H2 CAS awaiting→running recovery.

    Covers: task_not_found, already_terminal, not_awaiting,
            hitl_resume_not_requested, CAS lost (concurrent recovery),
            CAS win (successful recovery).
    """

    def test_task_not_found(self, mock_db):
        """Task not in DB → return False."""
        mock_db.get.return_value = None
        mocks, stop = _setup_hitl_resume_mocks(mock_db)

        try:
            result = process_hitl_resume(uuid4())
        finally:
            stop()

        assert result is False
        mock_db.execute.assert_not_called()
        mocks["process_task"].assert_not_called()

    def test_already_terminal(self, mock_db):
        """Already terminal → return False."""
        task = _make_task(status="succeeded", finished_at="2024-01-01T00:00:00")
        mock_db.get.return_value = task
        mocks, stop = _setup_hitl_resume_mocks(mock_db)

        try:
            result = process_hitl_resume(task.id)
        finally:
            stop()

        assert result is False
        mock_db.execute.assert_not_called()
        mocks["process_task"].assert_not_called()

    def test_not_awaiting_approval(self, mock_db):
        """status='running' (not awaiting) → return False."""
        task = _make_task(
            status="running",
            hitl_resume_requested=True,
        )
        mock_db.get.return_value = task
        mocks, stop = _setup_hitl_resume_mocks(mock_db)

        try:
            result = process_hitl_resume(task.id)
        finally:
            stop()

        assert result is False
        mock_db.execute.assert_not_called()
        mocks["process_task"].assert_not_called()

    def test_hitl_resume_not_requested(self, mock_db):
        """awaiting_approval but hitl_resume_requested=False → return False."""
        task = _make_task(
            status="awaiting_approval",
            hitl_resume_requested=False,
        )
        mock_db.get.return_value = task
        mocks, stop = _setup_hitl_resume_mocks(mock_db)

        try:
            result = process_hitl_resume(task.id)
        finally:
            stop()

        assert result is False
        mock_db.execute.assert_not_called()
        mocks["process_task"].assert_not_called()

    def test_cas_lost(self, mock_db):
        """CAS rowcount=0 (concurrent recovery) → return False, no process_task."""
        task = _make_task(
            status="awaiting_approval",
            hitl_resume_requested=True,
        )
        mock_db.get.return_value = task
        # Simulate CAS loss: another worker already claimed the resume
        mock_db.execute.return_value.rowcount = 0
        mocks, stop = _setup_hitl_resume_mocks(mock_db)

        try:
            result = process_hitl_resume(task.id)
        finally:
            stop()

        assert result is False
        mock_db.execute.assert_called_once()
        mocks["process_task"].assert_not_called()
        mock_db.refresh.assert_called()

    def test_cas_win(self, mock_db):
        """CAS rowcount=1 → return True, process_task called, result_json updated."""
        task = _make_task(
            status="awaiting_approval",
            hitl_resume_requested=True,
            result_json={"sql": "SELECT 1", "platform": {"hitl": {"phase": "awaiting"}}},
        )
        mock_db.get.return_value = task
        mock_db.execute.return_value.rowcount = 1
        mocks, stop = _setup_hitl_resume_mocks(mock_db)

        try:
            result = process_hitl_resume(task.id)
        finally:
            stop()

        assert result is True
        mock_db.execute.assert_called_once()
        mocks["process_task"].assert_called_once_with(task.id)

        # Verify result_json was updated with HITL execute phase metadata
        mocks["rl_attach"].assert_called_once()
        call_args = mocks["rl_attach"].call_args
        mocks["log_run"].assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3.3: _mark_hitl_snapshot_failed — HITL execute snapshot failure
# ═══════════════════════════════════════════════════════════════════════════


def _setup_snapshot_mocks(mock_db):
    """Start patches for _mark_hitl_snapshot_failed. Returns (mocks, stop_fn)."""
    _patchers = []
    _mocks = {}

    def _start(name: str, target: str, **kw: object) -> MagicMock:
        p = patch(target, **kw)
        _patchers.append(p)
        m = p.start()
        _mocks[name] = m
        return m

    _start("attach_run_platform",
           "app.workers.analysis_worker.rl.attach_run_platform",
           side_effect=lambda base, **kw: {
               **base,
               "_platform": {**base.get("platform", {}), **kw},
           })
    _start("apply_trace_columns",
           "app.workers.analysis_worker.rl.apply_trace_columns",
           return_value=None)
    _start("next_step_no",
           "app.workers.analysis_worker._next_step_no",
           return_value=3)
    _start("observe_terminal",
           "app.workers.analysis_worker._observe_terminal",
           return_value=None)
    _start("log_run",
           "app.workers.analysis_worker.log_run",
           return_value=None)
    _start("snapshot_check_payload",
           "agent.hitl_snapshot.snapshot_check_payload",
           return_value={"reason_code": "hash_mismatch", "details": "mocked"})

    def _stop() -> None:
        for p in reversed(_patchers):
            p.stop()

    return _mocks, _stop


def _make_verify_result(message="SQL hash mismatch: expected abc, got def",
                        reason_code="hash_mismatch"):
    """Factory for a mock verify_result with .message and .reason_code."""
    vr = MagicMock()
    vr.message = message
    vr.reason_code = reason_code
    return vr


class TestMarkHitlSnapshotFailed:
    """_mark_hitl_snapshot_failed: HITL execute snapshot check failure → terminal.

    Covers: normal snapshot failure, limitations merging,
            AgentRunStep creation, external call verification,
            platform.hitl field updates.
    """

    def test_normal_snapshot_failure(self, mock_db):
        """running → failed: status, failure_class, error_message, finished_at set."""
        task = _make_task(
            status="running",
            result_json={"sql": "SELECT 1"},
        )
        verify_result = _make_verify_result()
        mocks, stop = _setup_snapshot_mocks(mock_db)

        try:
            _mark_hitl_snapshot_failed(mock_db, task, verify_result)
        finally:
            stop()

        assert task.status == "failed"
        assert task.failure_class == "hitl_snapshot_mismatch"
        assert "hash mismatch" in task.error_message
        assert task.finished_at is not None

        # result_json updated
        assert isinstance(task.result_json, dict)
        assert "_platform" in task.result_json
        assert task.result_json["_platform"]["status"] == "failed"
        assert task.result_json["_platform"]["failure_class"] == "hitl_snapshot_mismatch"

    def test_limitations_merged(self, mock_db):
        """Existing limitations preserved, snapshot note appended."""
        task = _make_task(
            status="running",
            result_json={
                "sql": "SELECT 1",
                "limitations": ["Existing limitation"],
            },
        )
        verify_result = _make_verify_result()
        mocks, stop = _setup_snapshot_mocks(mock_db)

        try:
            _mark_hitl_snapshot_failed(mock_db, task, verify_result)
        finally:
            stop()

        assert "limitations" in task.result_json
        assert "Existing limitation" in task.result_json["limitations"]
        assert any("HITL: snapshot check failed" in item for item in task.result_json["limitations"])

    def test_limitations_no_duplicate(self, mock_db):
        """Same limitation note not duplicated on repeated calls."""
        existing_note = "HITL: snapshot check failed — hash mismatch"
        task = _make_task(
            status="running",
            result_json={"limitations": [existing_note]},
        )
        verify_result = _make_verify_result(message="hash mismatch")
        mocks, stop = _setup_snapshot_mocks(mock_db)

        try:
            _mark_hitl_snapshot_failed(mock_db, task, verify_result)
        finally:
            stop()

        # Count occurrences of the note
        count = sum(1 for item in task.result_json["limitations"] if "HITL: snapshot check failed" in item)
        assert count == 1

    def test_agent_run_step_created(self, mock_db):
        """AgentRunStep added to db with correct fields."""
        task = _make_task(status="running")
        verify_result = _make_verify_result()
        mocks, stop = _setup_snapshot_mocks(mock_db)

        try:
            _mark_hitl_snapshot_failed(mock_db, task, verify_result)
        finally:
            stop()

        # db.add called twice: once for AgentRunStep, once for task
        assert mock_db.add.call_count == 2
        # First call should be AgentRunStep
        step_call = mock_db.add.call_args_list[0]
        step = step_call[0][0]
        assert step.task_id == task.id
        assert step.node_name == "hitl_snapshot_check"
        assert step.status == "error"
        assert step.input_json == {"phase": "execute"}
        assert "hash mismatch" in step.error_message

    def test_external_calls(self, mock_db):
        """_observe_terminal, log_run, rl_attach, rl_apply all called."""
        task = _make_task(status="running")
        verify_result = _make_verify_result()
        mocks, stop = _setup_snapshot_mocks(mock_db)

        try:
            _mark_hitl_snapshot_failed(mock_db, task, verify_result)
        finally:
            stop()

        mocks["observe_terminal"].assert_called_once_with(task)
        mocks["log_run"].assert_called_once()
        mocks["attach_run_platform"].assert_called_once()
        mocks["apply_trace_columns"].assert_called_once_with(task, task.result_json)
        mocks["snapshot_check_payload"].assert_called_with(verify_result)
        assert mocks["snapshot_check_payload"].call_count == 2  # once for hitl, once for step
        mocks["next_step_no"].assert_called_once()
        mock_db.commit.assert_called_once()

    def test_platform_hitl_updated(self, mock_db):
        """platform.hitl has execute_error, snapshot_check, executed=False."""
        task = _make_task(
            status="running",
            result_json={"platform": {"hitl": {"phase": "awaiting"}}},
        )
        verify_result = _make_verify_result(
            message="SQL structure changed during approval",
            reason_code="structure_changed",
        )
        mocks, stop = _setup_snapshot_mocks(mock_db)

        try:
            _mark_hitl_snapshot_failed(mock_db, task, verify_result)
        finally:
            stop()

        assert "_platform" in task.result_json
        platform = task.result_json["_platform"]
        assert "hitl" in platform
        assert platform["hitl"]["phase"] == "execute"
        assert platform["hitl"]["decision"] == "approved"
        assert platform["hitl"]["executed"] is False
        assert "structure changed" in platform["hitl"]["execute_error"]
        assert "snapshot_check" in platform["hitl"]

    def test_error_message_truncated(self, mock_db):
        """error_message truncated to 2000 chars."""
        long_message = "x" * 3000
        task = _make_task(status="running")
        verify_result = _make_verify_result(message=long_message)
        mocks, stop = _setup_snapshot_mocks(mock_db)

        try:
            _mark_hitl_snapshot_failed(mock_db, task, verify_result)
        finally:
            stop()

        assert len(task.error_message) == 2000

    def test_null_result_json_defaults(self, mock_db):
        """result_json=None → handles gracefully, no crash."""
        task = _make_task(status="running", result_json=None)
        verify_result = _make_verify_result()
        mocks, stop = _setup_snapshot_mocks(mock_db)

        try:
            _mark_hitl_snapshot_failed(mock_db, task, verify_result)
        finally:
            stop()

        assert task.status == "failed"
        assert isinstance(task.result_json, dict)
        assert "_platform" in task.result_json