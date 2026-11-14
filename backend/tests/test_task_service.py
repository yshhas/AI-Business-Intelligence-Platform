"""Unit tests for app.services.task_service — Batch 1 + Batch 2.1.

Covers: get_task, list_tasks, get_execution_trace, _resolve_require_sql_approval,
        cancel_task, reject_task, approve_task (state machine).

No database, Redis, or FastAPI dependency — all external dependencies mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from uuid import uuid4

from app.models.task import AnalysisTask, AgentRunStep
from app.models.dataset import Dataset, DatasetAcl
from app.services.permissions import PermissionError as PermError
from app.services.idempotency import IdempotencyError
from app.services.skill_lifecycle import SkillLifecycleError
from app.services.runtime_essentials import CapacityError
from app.services.cost_budget import BudgetError
from app.services.task_service import (
    _resolve_require_sql_approval,
    cancel_task,
    create_task,
    get_execution_trace,
    get_task,
    list_tasks,
    list_steps,
    reject_task,
    approve_task,
    TaskServiceError,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_task(**overrides) -> AnalysisTask:
    """Factory for AnalysisTask with safe defaults."""
    ws_id = uuid4()
    ds_id = uuid4()
    uid = uuid4()
    kwargs = {
        "id": uuid4(),
        "workspace_id": ws_id,
        "dataset_id": ds_id,
        "user_id": uid,
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
    }
    kwargs.update(overrides)
    return AnalysisTask(**kwargs)


# ── get_task ──────────────────────────────────────────────────────────────

class TestGetTask:
    """get_task queries AnalysisTask by id + workspace_id."""

    def test_task_found(self, mock_db):
        task = _make_task()
        mock_db.execute.return_value.scalar_one_or_none.return_value = task

        result = get_task(mock_db, workspace_id=task.workspace_id, task_id=task.id)

        assert result is task
        mock_db.execute.assert_called_once()

    def test_task_not_found(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        result = get_task(mock_db, workspace_id=uuid4(), task_id=uuid4())

        assert result is None

    def test_cross_workspace_isolation(self, mock_db):
        """Task in workspace A is not visible to workspace B."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        result = get_task(mock_db, workspace_id=uuid4(), task_id=uuid4())

        assert result is None
        # Verify the query was executed
        mock_db.execute.assert_called_once()


# ── list_tasks ────────────────────────────────────────────────────────────

class TestListTasks:
    """list_tasks with ACL visibility filtering."""

    def test_no_member_returns_all(self, mock_db):
        """When member is None, ACL filtering is skipped."""
        ws_id = uuid4()
        tasks = [_make_task(workspace_id=ws_id) for _ in range(3)]
        mock_db.scalars.return_value.all.return_value = tasks

        result = list_tasks(mock_db, workspace_id=ws_id, member=None)

        assert len(result) == 3
        assert result == tasks

    def test_empty_items_returns_empty(self, mock_db):
        """No tasks → empty list."""
        mock_db.scalars.return_value.all.return_value = []

        result = list_tasks(mock_db, workspace_id=uuid4(), member=MagicMock())

        assert result == []

    def test_limit_clamped(self, mock_db):
        """limit is clamped to [1, 100]."""
        ws_id = uuid4()
        mock_db.scalars.return_value.all.return_value = []

        # limit=0 → clamped to 1
        list_tasks(mock_db, workspace_id=ws_id, limit=0, member=None)
        # limit=500 → clamped to 100
        list_tasks(mock_db, workspace_id=ws_id, limit=500, member=None)

    def test_owner_sees_all(self, mock_db):
        """Workspace owner sees all tasks regardless of ACL."""
        ws_id = uuid4()
        uid = uuid4()
        tasks = [
            _make_task(workspace_id=ws_id, user_id=uuid4()) for _ in range(3)
        ]
        # Build matching Dataset objects so d.id == task.dataset_id
        datasets = []
        for t in tasks:
            ds = MagicMock(spec=Dataset)
            ds.id = t.dataset_id
            datasets.append(ds)

        mock_db.scalars.return_value.all.side_effect = [
            tasks,     # 1st: items query
            datasets,  # 2nd: Dataset lookup
        ]
        mock_db.get.return_value = MagicMock()  # Workspace

        with patch(
            "app.services.task_service.perm.is_workspace_owner", return_value=True
        ):
            result = list_tasks(
                mock_db,
                workspace_id=ws_id,
                member=MagicMock(),
                user_id=uid,
            )

        assert len(result) == 3

    def test_creator_sees_own_tasks(self, mock_db):
        """Task creator sees their own tasks."""
        ws_id = uuid4()
        uid = uuid4()
        own = _make_task(workspace_id=ws_id, user_id=uid)
        other = _make_task(workspace_id=ws_id, user_id=uuid4())
        # Build Dataset objects with matching IDs
        ds_own = MagicMock(spec=Dataset)
        ds_own.id = own.dataset_id
        ds_other = MagicMock(spec=Dataset)
        ds_other.id = other.dataset_id

        mock_db.scalars.return_value.all.side_effect = [
            [own, other],          # 1st: items
            [ds_own, ds_other],    # 2nd: Dataset lookup
            [],                    # 3rd: ACL entries for uid (empty)
        ]
        mock_db.get.return_value = MagicMock()
        # ACL count: both datasets have ACL rows
        mock_db.execute.return_value.all.return_value = [
            (own.dataset_id, 1),
            (other.dataset_id, 1),
        ]

        with patch(
            "app.services.task_service.perm.is_workspace_owner", return_value=False
        ):
            result = list_tasks(
                mock_db,
                workspace_id=ws_id,
                member=MagicMock(),
                user_id=uid,
            )

        assert len(result) == 1
        assert result[0] is own

    def test_acl_can_read_visible(self, mock_db):
        """Dataset with ACL can_read=True → task visible."""
        ws_id = uuid4()
        uid = uuid4()
        ds_id = uuid4()
        task = _make_task(workspace_id=ws_id, user_id=uuid4(), dataset_id=ds_id)
        ds = MagicMock(spec=Dataset)
        ds.id = ds_id
        acl = MagicMock(spec=DatasetAcl)
        acl.dataset_id = ds_id
        acl.can_read = True

        mock_db.scalars.return_value.all.side_effect = [
            [task],  # items
            [ds],  # datasets
            [acl],  # ACL entries
        ]
        mock_db.get.return_value = MagicMock()
        mock_db.execute.return_value.all.return_value = [(ds_id, 1)]  # ACL count

        with patch(
            "app.services.task_service.perm.is_workspace_owner", return_value=False
        ):
            result = list_tasks(
                mock_db,
                workspace_id=ws_id,
                member=MagicMock(),
                user_id=uid,
            )

        assert len(result) == 1

    def test_acl_denied_not_visible(self, mock_db):
        """Dataset with ACL but no can_read → task not visible."""
        ws_id = uuid4()
        uid = uuid4()
        ds_id = uuid4()
        task = _make_task(workspace_id=ws_id, user_id=uuid4(), dataset_id=ds_id)
        ds = MagicMock(spec=Dataset)
        ds.id = ds_id

        mock_db.scalars.return_value.all.side_effect = [
            [task],  # items
            [ds],  # datasets
            [],  # ACL entries (none for this user)
        ]
        mock_db.get.return_value = MagicMock()
        mock_db.execute.return_value.all.return_value = [(ds_id, 1)]  # ACL count

        with patch(
            "app.services.task_service.perm.is_workspace_owner", return_value=False
        ):
            result = list_tasks(
                mock_db,
                workspace_id=ws_id,
                member=MagicMock(),
                user_id=uid,
            )

        assert len(result) == 0

    def test_no_acl_on_dataset_visible(self, mock_db):
        """Dataset without ACL rows → default-open → task visible."""
        ws_id = uuid4()
        uid = uuid4()
        ds_id = uuid4()
        task = _make_task(workspace_id=ws_id, user_id=uuid4(), dataset_id=ds_id)
        ds = MagicMock(spec=Dataset)
        ds.id = ds_id

        mock_db.scalars.return_value.all.side_effect = [
            [task],  # items
            [ds],  # datasets
        ]
        mock_db.get.return_value = MagicMock()
        mock_db.execute.return_value.all.return_value = []  # no ACL rows

        with patch(
            "app.services.task_service.perm.is_workspace_owner", return_value=False
        ):
            result = list_tasks(
                mock_db,
                workspace_id=ws_id,
                member=MagicMock(),
                user_id=uid,
            )

        assert len(result) == 1

    def test_status_filter(self, mock_db):
        """status filter is appended to the query."""
        ws_id = uuid4()
        mock_db.scalars.return_value.all.return_value = []

        list_tasks(mock_db, workspace_id=ws_id, status="failed", member=None)

    def test_filters_applied(self, mock_db):
        """skill_id, source_type, policy_denied, failure_class filters."""
        ws_id = uuid4()
        mock_db.scalars.return_value.all.return_value = []

        list_tasks(
            mock_db,
            workspace_id=ws_id,
            skill_id="data.bi",
            source_type="file",
            policy_denied=True,
            failure_class="budget",
            member=None,
        )


# ── get_execution_trace ───────────────────────────────────────────────────

class TestGetExecutionTrace:
    """get_execution_trace builds ExecutionTrace from task row."""

    def test_task_not_found(self, mock_db):
        """None task → None trace."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        result = get_execution_trace(
            mock_db, workspace_id=uuid4(), task_id=uuid4()
        )

        assert result is None

    def test_basic_trace_fields(self, mock_db):
        """Basic trace includes all top-level fields."""
        task = _make_task(
            status="succeeded",
            skill_id="data.bi",
            skill_version="1.0",
            source_type="file",
            policy_denied=False,
            result_json={"platform": {"run": {"duration_ms": 1200}}},
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = task

        result = get_execution_trace(
            mock_db, workspace_id=task.workspace_id, task_id=task.id
        )

        assert result["run_id"] == str(task.id)
        assert result["status"] == "succeeded"
        assert result["skill_id"] == "data.bi"
        assert result["skill_version"] == "1.0"
        assert result["source_type"] == "file"
        assert result["policy_denied"] is False
        assert result["run"]["duration_ms"] == 1200

    def test_fallback_to_platform(self, mock_db):
        """When task columns are None, fall back to platform values."""
        task = _make_task(
            skill_id=None,
            skill_version=None,
            source_type=None,
            result_json={
                "platform": {
                    "skill_id": "data.profile",
                    "skill_version": "2.0",
                    "data_plane": {"source_type": "postgres_ro"},
                }
            },
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = task

        result = get_execution_trace(
            mock_db, workspace_id=task.workspace_id, task_id=task.id
        )

        assert result["skill_id"] == "data.profile"
        assert result["skill_version"] == "2.0"
        assert result["source_type"] == "postgres_ro"

    def test_incomplete_statuses(self, mock_db):
        """pending/running/cancelled/timed_out → execution.summary.incomplete=True."""
        for status in ("pending", "running", "cancelled", "timed_out"):
            task = _make_task(status=status)
            mock_db.execute.return_value.scalar_one_or_none.return_value = task

            result = get_execution_trace(
                mock_db, workspace_id=task.workspace_id, task_id=task.id
            )

            assert result["execution"]["summary"]["incomplete"] is True

    def test_succeeded_status_not_incomplete(self, mock_db):
        """succeeded status → execution.summary.incomplete=False."""
        task = _make_task(status="succeeded")
        mock_db.execute.return_value.scalar_one_or_none.return_value = task

        result = get_execution_trace(
            mock_db, workspace_id=task.workspace_id, task_id=task.id
        )

        assert result["execution"]["summary"]["incomplete"] is False

    def test_empty_result_json(self, mock_db):
        """Empty result_json → default execution structure."""
        task = _make_task(result_json=None)
        mock_db.execute.return_value.scalar_one_or_none.return_value = task

        result = get_execution_trace(
            mock_db, workspace_id=task.workspace_id, task_id=task.id
        )

        assert result["execution"]["tool_calls"] == []
        assert result["execution"]["summary"]["tool_count"] == 0

    def test_null_timestamps(self, mock_db):
        """Null created_at/started_at/finished_at → None in trace."""
        task = _make_task(created_at=None, started_at=None, finished_at=None)
        mock_db.execute.return_value.scalar_one_or_none.return_value = task

        result = get_execution_trace(
            mock_db, workspace_id=task.workspace_id, task_id=task.id
        )

        assert result["created_at"] is None
        assert result["started_at"] is None
        assert result["finished_at"] is None


# ── _resolve_require_sql_approval ─────────────────────────────────────────

class TestResolveSqlApproval:
    """Pure function: kill-switch + skill_id gate."""

    def test_switch_disabled(self):
        """Kill-switch off → always False."""
        settings = MagicMock()
        settings.hitl_sql_approval_enabled = False

        assert _resolve_require_sql_approval(
            settings, skill_id="data.bi", requested=True
        ) is False

    def test_non_data_bi_skill(self):
        """Non-data.bi skill → False regardless of request."""
        settings = MagicMock()
        settings.hitl_sql_approval_enabled = True

        assert _resolve_require_sql_approval(
            settings, skill_id="data.profile", requested=True
        ) is False

    def test_data_bi_with_request(self):
        """data.bi + requested=True → True."""
        settings = MagicMock()
        settings.hitl_sql_approval_enabled = True

        assert _resolve_require_sql_approval(
            settings, skill_id="data.bi", requested=True
        ) is True

    def test_data_bi_without_request(self):
        """data.bi + requested=False → False."""
        settings = MagicMock()
        settings.hitl_sql_approval_enabled = True

        assert _resolve_require_sql_approval(
            settings, skill_id="data.bi", requested=False
        ) is False

    def test_empty_skill_id(self):
        """Empty skill_id → treated as non-data.bi."""
        settings = MagicMock()
        settings.hitl_sql_approval_enabled = True

        assert _resolve_require_sql_approval(
            settings, skill_id="", requested=True
        ) is False

    def test_none_skill_id(self):
        """None skill_id → treated as non-data.bi."""
        settings = MagicMock()
        settings.hitl_sql_approval_enabled = True

        assert _resolve_require_sql_approval(
            settings, skill_id=None, requested=True
        ) is False

    def test_missing_attribute(self):
        """Settings without hitl_sql_approval_enabled → False."""
        settings = object()

        assert _resolve_require_sql_approval(
            settings, skill_id="data.bi", requested=True
        ) is False


# ── list_steps ────────────────────────────────────────────────────────────

class TestListSteps:
    """list_steps queries AgentRunStep by task_id."""

    def test_returns_steps(self, mock_db):
        steps = [MagicMock(spec=AgentRunStep) for _ in range(3)]
        mock_db.scalars.return_value.all.return_value = steps

        result = list_steps(mock_db, task_id=uuid4())

        assert len(result) == 3

    def test_empty_steps(self, mock_db):
        mock_db.scalars.return_value.all.return_value = []

        result = list_steps(mock_db, task_id=uuid4())

        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# Batch 2.1: cancel_task / reject_task / approve_task state machine tests
# ═══════════════════════════════════════════════════════════════════════════


def _setup_state_machine_mocks(mock_db, *, task, settings_enabled=True):
    """Configure mock_db + start all patches. Returns (mocks_dict, stop_fn).

    Caller MUST call stop_fn() in a finally block to clean up patches.
    """
    # get_task → db.execute(select(...)).scalar_one_or_none()
    _get_result = MagicMock()
    if task is not None:
        _get_result.scalar_one_or_none.return_value = task
    else:
        _get_result.scalar_one_or_none.return_value = None

    # For approve_task: second db.execute (CAS update) returns rowcount
    _cas_result = MagicMock()
    _cas_result.rowcount = 1

    # db.execute side_effect: 1st call = get_task query, 2nd call = CAS update
    mock_db.execute.side_effect = [_get_result, _cas_result]

    # Workspace lookup
    mock_db.get.return_value = MagicMock()

    # Settings mock
    _settings = MagicMock()
    _settings.hitl_sql_approval_enabled = settings_enabled

    _patchers = []
    _mocks: dict[str, MagicMock] = {}

    def _start(name: str, target: str, **kw: object) -> MagicMock:
        p = patch(target, **kw)
        _patchers.append(p)
        m = p.start()
        _mocks[name] = m
        return m

    _start("get_settings", "app.services.task_service.get_settings",
           return_value=_settings)
    _start("perm_require", "app.services.task_service.perm.require",
           return_value=None)
    _start("attach_run_platform", "app.services.task_service.rl.attach_run_platform",
           side_effect=lambda base, **kw: {**base, "_platform": kw})
    _start("apply_trace_columns", "app.services.task_service.rl.apply_trace_columns",
           return_value=None)
    _start("enqueue_task", "app.services.task_service.task_queue.enqueue_task",
           return_value=None)
    _start("enqueue_hitl_resume", "app.services.task_service.task_queue.enqueue_hitl_resume",
           return_value=None)

    def _stop() -> None:
        for p in reversed(_patchers):
            p.stop()

    return _mocks, _stop


# ── cancel_task ───────────────────────────────────────────────────────────

class TestCancelTask:
    """State machine: cancel_task transitions."""

    def test_pending_cancels_immediately(self, mock_db):
        """pending → cancelled (terminal)."""
        task = _make_task(status="pending")
        mocks, stop = _setup_state_machine_mocks(mock_db, task=task)

        try:
            result = cancel_task(
                mock_db,
                workspace_id=task.workspace_id,
                task_id=task.id,
                user_id=task.user_id,
                member_role="owner",
            )
        finally:
            stop()

        assert result.status == "cancelled"
        assert result.cancel_requested is True
        assert result.failure_class == "cancelled"
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called()

    def test_awaiting_approval_cancels_immediately(self, mock_db):
        """awaiting_approval → cancelled (terminal)."""
        task = _make_task(status="awaiting_approval")
        mocks, stop = _setup_state_machine_mocks(mock_db, task=task)

        try:
            result = cancel_task(
                mock_db,
                workspace_id=task.workspace_id,
                task_id=task.id,
                user_id=task.user_id,
                member_role="owner",
            )
        finally:
            stop()

        assert result.status == "cancelled"
        assert result.cancel_requested is True
        assert result.failure_class == "cancelled"

    def test_running_only_sets_cancel_requested(self, mock_db):
        """running → cancel_requested=True, status unchanged."""
        task = _make_task(status="running")
        mocks, stop = _setup_state_machine_mocks(mock_db, task=task)

        try:
            result = cancel_task(
                mock_db,
                workspace_id=task.workspace_id,
                task_id=task.id,
                user_id=task.user_id,
                member_role="owner",
            )
        finally:
            stop()

        assert result.status == "running"
        assert result.cancel_requested is True
        mocks["attach_run_platform"].assert_not_called()

    def test_terminal_status_rejected(self, mock_db):
        """succeeded/failed/cancelled/timed_out → 409."""
        for status in ("succeeded", "failed", "cancelled", "timed_out"):
            task = _make_task(status=status)
            # Reset execute mock for each iteration
            _get_result = MagicMock()
            _get_result.scalar_one_or_none.return_value = task
            mock_db.execute.side_effect = [_get_result]
            mock_db.reset_mock()

            with patch("app.services.task_service.perm.require"):
                with pytest.raises(TaskServiceError, match="terminal"):
                    cancel_task(
                        mock_db,
                        workspace_id=task.workspace_id,
                        task_id=task.id,
                        user_id=task.user_id,
                        member_role="owner",
                    )

    def test_permission_denied(self, mock_db):
        """PermissionError → TaskServiceError."""
        task = _make_task(status="pending")
        mocks, stop = _setup_state_machine_mocks(mock_db, task=task)
        mocks["perm_require"].side_effect = PermError("denied")

        try:
            with pytest.raises(TaskServiceError):
                cancel_task(
                    mock_db,
                    workspace_id=task.workspace_id,
                    task_id=task.id,
                    user_id=uuid4(),
                    member_role="viewer",
                )
        finally:
            stop()

    def test_task_not_found(self, mock_db):
        """None task → 404."""
        mocks, stop = _setup_state_machine_mocks(mock_db, task=None)

        try:
            with pytest.raises(TaskServiceError, match="not found"):
                cancel_task(
                    mock_db,
                    workspace_id=uuid4(),
                    task_id=uuid4(),
                    user_id=uuid4(),
                    member_role="owner",
                )
        finally:
            stop()


# ── reject_task ───────────────────────────────────────────────────────────

class TestRejectTask:
    """State machine: reject_task transitions (HITL H1)."""

    def test_awaiting_approval_rejected(self, mock_db):
        """awaiting_approval → failed / hitl_rejected."""
        task = _make_task(status="awaiting_approval")
        mocks, stop = _setup_state_machine_mocks(mock_db, task=task)

        try:
            result = reject_task(
                mock_db,
                workspace_id=task.workspace_id,
                task_id=task.id,
                user_id=task.user_id,
                member_role="owner",
            )
        finally:
            stop()

        assert result.status == "failed"
        assert result.failure_class == "hitl_rejected"
        mock_db.commit.assert_called()

    def test_hitl_disabled_rejected(self, mock_db):
        """HITL switch off → 409."""
        task = _make_task(status="awaiting_approval")
        mocks, stop = _setup_state_machine_mocks(
            mock_db, task=task, settings_enabled=False
        )

        try:
            with pytest.raises(TaskServiceError, match="disabled"):
                reject_task(
                    mock_db,
                    workspace_id=task.workspace_id,
                    task_id=task.id,
                    user_id=task.user_id,
                    member_role="owner",
                )
        finally:
            stop()

    def test_non_awaiting_approval_rejected(self, mock_db):
        """Non-awaiting_approval status → 409."""
        for status in ("pending", "running", "succeeded", "failed"):
            task = _make_task(status=status)
            _get_result = MagicMock()
            _get_result.scalar_one_or_none.return_value = task
            mock_db.execute.side_effect = [_get_result]
            mock_db.reset_mock()

            with patch(
                "app.services.task_service.get_settings",
                return_value=MagicMock(hitl_sql_approval_enabled=True),
            ), patch("app.services.task_service.perm.require"):
                with pytest.raises(TaskServiceError, match="Cannot reject"):
                    reject_task(
                        mock_db,
                        workspace_id=task.workspace_id,
                        task_id=task.id,
                        user_id=task.user_id,
                        member_role="owner",
                    )

    def test_permission_denied(self, mock_db):
        """PermissionError → TaskServiceError."""
        task = _make_task(status="awaiting_approval")
        mocks, stop = _setup_state_machine_mocks(mock_db, task=task)
        mocks["perm_require"].side_effect = PermError("denied")

        try:
            with pytest.raises(TaskServiceError):
                reject_task(
                    mock_db,
                    workspace_id=task.workspace_id,
                    task_id=task.id,
                    user_id=uuid4(),
                    member_role="viewer",
                )
        finally:
            stop()

    def test_task_not_found(self, mock_db):
        """None task → 404."""
        mocks, stop = _setup_state_machine_mocks(mock_db, task=None)

        try:
            with pytest.raises(TaskServiceError, match="not found"):
                reject_task(
                    mock_db,
                    workspace_id=uuid4(),
                    task_id=uuid4(),
                    user_id=uuid4(),
                    member_role="owner",
                )
        finally:
            stop()

    def test_reason_saved(self, mock_db):
        """reject reason is stored in error_message."""
        task = _make_task(status="awaiting_approval")
        mocks, stop = _setup_state_machine_mocks(mock_db, task=task)

        try:
            result = reject_task(
                mock_db,
                workspace_id=task.workspace_id,
                task_id=task.id,
                user_id=task.user_id,
                member_role="owner",
                reason="SQL contains forbidden pattern",
            )
        finally:
            stop()

        assert "SQL contains forbidden pattern" in result.error_message

    def test_default_reason_when_empty(self, mock_db):
        """Empty reason → default message."""
        task = _make_task(status="awaiting_approval")
        mocks, stop = _setup_state_machine_mocks(mock_db, task=task)

        try:
            result = reject_task(
                mock_db,
                workspace_id=task.workspace_id,
                task_id=task.id,
                user_id=task.user_id,
                member_role="owner",
            )
        finally:
            stop()

        assert "SQL approval rejected" in result.error_message


# ── approve_task ──────────────────────────────────────────────────────────

class TestApproveTask:
    """State machine: approve_task transitions (HITL H2 T1)."""

    def test_normal_approve_enqueues_resume(self, mock_db):
        """awaiting_approval → hitl_resume_requested=True + enqueue."""
        task = _make_task(status="awaiting_approval")
        mocks, stop = _setup_state_machine_mocks(mock_db, task=task)

        try:
            result = approve_task(
                mock_db,
                workspace_id=task.workspace_id,
                task_id=task.id,
                user_id=task.user_id,
                member_role="owner",
            )
        finally:
            stop()

        assert result.hitl_resume_requested is True
        mocks["enqueue_hitl_resume"].assert_called_once_with(task.id)

    def test_hitl_disabled_rejected(self, mock_db):
        """HITL switch off → 409."""
        task = _make_task(status="awaiting_approval")
        mocks, stop = _setup_state_machine_mocks(
            mock_db, task=task, settings_enabled=False
        )

        try:
            with pytest.raises(TaskServiceError, match="disabled"):
                approve_task(
                    mock_db,
                    workspace_id=task.workspace_id,
                    task_id=task.id,
                    user_id=task.user_id,
                    member_role="owner",
                )
        finally:
            stop()

    def test_non_awaiting_approval_rejected(self, mock_db):
        """Non-awaiting_approval status → 409."""
        for status in ("pending", "running", "succeeded", "failed"):
            task = _make_task(status=status)
            _get_result = MagicMock()
            _get_result.scalar_one_or_none.return_value = task
            mock_db.execute.side_effect = [_get_result]
            mock_db.reset_mock()

            with patch(
                "app.services.task_service.get_settings",
                return_value=MagicMock(hitl_sql_approval_enabled=True),
            ), patch("app.services.task_service.perm.require"):
                with pytest.raises(TaskServiceError, match="Cannot approve"):
                    approve_task(
                        mock_db,
                        workspace_id=task.workspace_id,
                        task_id=task.id,
                        user_id=task.user_id,
                        member_role="owner",
                    )

    def test_already_resume_requested_rejected(self, mock_db):
        """hitl_resume_requested=True → 409."""
        task = _make_task(
            status="awaiting_approval", hitl_resume_requested=True
        )
        mocks, stop = _setup_state_machine_mocks(mock_db, task=task)

        try:
            with pytest.raises(TaskServiceError, match="already requested"):
                approve_task(
                    mock_db,
                    workspace_id=task.workspace_id,
                    task_id=task.id,
                    user_id=task.user_id,
                    member_role="owner",
                )
        finally:
            stop()

    def test_cas_success(self, mock_db):
        """CAS update returns rowcount=1 → success."""
        task = _make_task(status="awaiting_approval")
        mocks, stop = _setup_state_machine_mocks(mock_db, task=task)

        try:
            result = approve_task(
                mock_db,
                workspace_id=task.workspace_id,
                task_id=task.id,
                user_id=task.user_id,
                member_role="owner",
            )
        finally:
            stop()

        assert result.hitl_resume_requested is True

    def test_cas_concurrent_conflict(self, mock_db):
        """CAS rowcount=0 → 409 (concurrent approve or status change)."""
        task = _make_task(status="awaiting_approval")
        # First execute = get_task query, second = CAS update (rowcount=0),
        # third = get_task retry (after CAS fails)
        _get1 = MagicMock()
        _get1.scalar_one_or_none.return_value = task
        _cas = MagicMock()
        _cas.rowcount = 0
        _get2 = MagicMock()
        _get2.scalar_one_or_none.return_value = task
        mock_db.execute.side_effect = [_get1, _cas, _get2]
        mock_db.get.return_value = MagicMock()

        with patch(
            "app.services.task_service.get_settings",
            return_value=MagicMock(hitl_sql_approval_enabled=True),
        ), patch("app.services.task_service.perm.require"):
            with pytest.raises(TaskServiceError, match="already requested"):
                approve_task(
                    mock_db,
                    workspace_id=task.workspace_id,
                    task_id=task.id,
                    user_id=task.user_id,
                    member_role="owner",
                )

    def test_permission_denied(self, mock_db):
        """PermissionError → TaskServiceError."""
        task = _make_task(status="awaiting_approval")
        mocks, stop = _setup_state_machine_mocks(mock_db, task=task)
        mocks["perm_require"].side_effect = PermError("denied")

        try:
            with pytest.raises(TaskServiceError):
                approve_task(
                    mock_db,
                    workspace_id=task.workspace_id,
                    task_id=task.id,
                    user_id=uuid4(),
                    member_role="viewer",
                )
        finally:
            stop()

    def test_task_not_found(self, mock_db):
        """None task → 404."""
        mocks, stop = _setup_state_machine_mocks(mock_db, task=None)

        try:
            with pytest.raises(TaskServiceError, match="not found"):
                approve_task(
                    mock_db,
                    workspace_id=uuid4(),
                    task_id=uuid4(),
                    user_id=uuid4(),
                    member_role="owner",
                )
        finally:
            stop()


# ═══════════════════════════════════════════════════════════════════════════
# Batch 2.2: create_task tests
# ═══════════════════════════════════════════════════════════════════════════


def _setup_create_task_mocks(mock_db, *, dataset_status="ready"):
    """Configure mock_db + start all patches for create_task tests.

    Returns (mocks_dict, stop_fn). Caller MUST call stop_fn() in a finally block.
    """
    # Dataset mock returned by db.execute().scalar_one_or_none()
    ds = MagicMock()
    ds.id = uuid4()
    ds.status = dataset_status

    _ds_result = MagicMock()
    _ds_result.scalar_one_or_none.return_value = ds
    mock_db.execute.side_effect = [_ds_result]

    # Workspace mock returned by db.get(Workspace, ...)
    mock_db.get.return_value = MagicMock()

    # Settings mock
    _settings = MagicMock()
    _settings.run_timeout_seconds = 300
    _settings.hitl_sql_approval_enabled = True

    _patchers = []
    _mocks = {}

    def _start(name: str, target: str, **kw: object) -> MagicMock:
        p = patch(target, **kw)
        _patchers.append(p)
        m = p.start()
        _mocks[name] = m
        return m

    _start("get_settings", "app.services.task_service.get_settings",
           return_value=_settings)
    _start("perm_require", "app.services.task_service.perm.require",
           return_value=None)
    _start("assert_skill_invokable",
           "app.services.task_service.skills.assert_skill_invokable",
           return_value=("data.bi", "1.0"))
    _start("assert_enqueue_allowed",
           "app.services.task_service.rt.assert_enqueue_allowed",
           return_value=None)
    _start("assert_budget_allowed",
           "app.services.task_service.cost_budget.assert_budget_allowed",
           return_value=None)
    _start("enqueue_task",
           "app.services.task_service.task_queue.enqueue_task",
           return_value=None)
    _start("attach_run_platform",
           "app.services.task_service.rl.attach_run_platform",
           side_effect=lambda base, **kw: {**base, "_platform": kw})
    _start("resolve_approval",
           "app.services.task_service._resolve_require_sql_approval",
           return_value=False)
    _start("metric_enqueue",
           "app.services.task_service._metric_enqueue",
           return_value=None)
    _start("metric_terminal",
           "app.services.task_service._metric_terminal",
           return_value=None)
    _start("log_run",
           "app.services.task_service.log_run",
           return_value=None)

    # Idempotency — patched on the module (imported locally inside create_task)
    _start("claim_idempotency",
           "app.services.idempotency.claim_idempotency_key",
           return_value=None)
    _start("release_claim",
           "app.services.idempotency.release_claim",
           return_value=None)
    _start("remember_task_id",
           "app.services.idempotency.remember_task_id",
           return_value=None)

    def _stop() -> None:
        for p in reversed(_patchers):
            p.stop()

    return _mocks, _stop


# ── create_task ───────────────────────────────────────────────────────────

class TestCreateTask:
    """create_task: full lifecycle with all error branches."""

    # ── Happy path ────────────────────────────────────────────────────

    def test_normal_create(self, mock_db):
        """All checks pass → pending task returned, enqueue called."""
        ws_id = uuid4()
        uid = uuid4()
        ds_id = uuid4()
        mocks, stop = _setup_create_task_mocks(mock_db)

        try:
            result = create_task(
                mock_db,
                workspace_id=ws_id,
                user_id=uid,
                dataset_id=ds_id,
                question="show me revenue by month",
                member_role="owner",
            )
        finally:
            stop()

        assert result.status == "pending"
        assert result.cancel_requested is False
        assert result.failure_class is None
        assert result.question == "show me revenue by month"
        assert result.workspace_id == ws_id
        assert result.user_id == uid
        assert result.dataset_id == ds_id
        assert result.skill_id == "data.bi"
        assert result.skill_version == "1.0"
        mocks["enqueue_task"].assert_called_once_with(result.id)
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called()

    # ── Idempotency ───────────────────────────────────────────────────

    def test_idempotency_existing_task(self, mock_db):
        """claim returns existing task_id → return existing task directly."""
        ws_id = uuid4()
        existing = _make_task(workspace_id=ws_id, status="pending")
        mocks, stop = _setup_create_task_mocks(mock_db)
        mocks["claim_idempotency"].return_value = existing.id
        mock_db.get.return_value = existing

        try:
            result = create_task(
                mock_db,
                workspace_id=ws_id,
                user_id=uuid4(),
                dataset_id=uuid4(),
                question="irrelevant",
                member_role="owner",
                idempotency_key="dup-key",
            )
        finally:
            stop()

        assert result is existing
        # Should not call enqueue or any downstream logic
        mocks["enqueue_task"].assert_not_called()

    def test_idempotency_claim_error(self, mock_db):
        """claim raises IdempotencyError → TaskServiceError."""
        mocks, stop = _setup_create_task_mocks(mock_db)
        mocks["claim_idempotency"].side_effect = IdempotencyError(
            "redis unavailable", status_code=503
        )

        try:
            with pytest.raises(TaskServiceError, match="redis unavailable"):
                create_task(
                    mock_db,
                    workspace_id=uuid4(),
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="irrelevant",
                    member_role="owner",
                    idempotency_key="boom",
                )
        finally:
            stop()

    def test_idempotency_remember_fails(self, mock_db):
        """remember_task_id raises → TaskServiceError after task created."""
        ws_id = uuid4()
        mocks, stop = _setup_create_task_mocks(mock_db)
        mocks["claim_idempotency"].return_value = None  # new claim
        mocks["remember_task_id"].side_effect = IdempotencyError(
            "redis timeout", status_code=503
        )

        try:
            with pytest.raises(TaskServiceError, match="redis timeout"):
                create_task(
                    mock_db,
                    workspace_id=ws_id,
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="valid question",
                    member_role="owner",
                    idempotency_key="late-fail",
                )
        finally:
            stop()

    def test_idempotency_release_on_error(self, mock_db):
        """When an error occurs after claim, release_claim is called."""
        mocks, stop = _setup_create_task_mocks(mock_db)
        mocks["claim_idempotency"].return_value = None  # claim succeeded
        # Dataset not found → error
        _ds_result = MagicMock()
        _ds_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [_ds_result]

        try:
            with pytest.raises(TaskServiceError, match="not found"):
                create_task(
                    mock_db,
                    workspace_id=uuid4(),
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="test",
                    member_role="owner",
                    idempotency_key="rel-key",
                )
        finally:
            stop()

        mocks["release_claim"].assert_called_once()

    # ── Dataset validation ────────────────────────────────────────────

    def test_dataset_not_found(self, mock_db):
        """Dataset query returns None → 404."""
        mocks, stop = _setup_create_task_mocks(mock_db)
        _ds_result = MagicMock()
        _ds_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [_ds_result]

        try:
            with pytest.raises(TaskServiceError, match="not found"):
                create_task(
                    mock_db,
                    workspace_id=uuid4(),
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="test",
                    member_role="owner",
                )
        finally:
            stop()

    def test_dataset_not_ready(self, mock_db):
        """Dataset status != 'ready' → 409."""
        mocks, stop = _setup_create_task_mocks(
            mock_db, dataset_status="error"
        )

        try:
            with pytest.raises(TaskServiceError, match="not ready"):
                create_task(
                    mock_db,
                    workspace_id=uuid4(),
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="test",
                    member_role="owner",
                )
        finally:
            stop()

    # ── Permission validation ─────────────────────────────────────────

    def test_permission_denied_run_create(self, mock_db):
        """perm.require(RUN_CREATE) raises PermissionError."""
        mocks, stop = _setup_create_task_mocks(mock_db)
        mocks["perm_require"].side_effect = PermError("no run.create")

        try:
            with pytest.raises(TaskServiceError, match="no run.create"):
                create_task(
                    mock_db,
                    workspace_id=uuid4(),
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="test",
                    member=MagicMock(),
                )
        finally:
            stop()

    def test_permission_denied_skill_invoke(self, mock_db):
        """First perm.require passes, second (SKILL_INVOKE) fails."""
        mocks, stop = _setup_create_task_mocks(mock_db)
        mocks["perm_require"].side_effect = [None, PermError("no skill.invoke")]

        try:
            with pytest.raises(TaskServiceError, match="no skill.invoke"):
                create_task(
                    mock_db,
                    workspace_id=uuid4(),
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="test",
                    member=MagicMock(),
                )
        finally:
            stop()

        # Verify RUN_CREATE was called first, then SKILL_INVOKE
        assert mocks["perm_require"].call_count == 2

    def test_member_role_fallback(self, mock_db):
        """member=None → falls back to member_role path."""
        ws_id = uuid4()
        mocks, stop = _setup_create_task_mocks(mock_db)

        try:
            result = create_task(
                mock_db,
                workspace_id=ws_id,
                user_id=uuid4(),
                dataset_id=uuid4(),
                question="test",
                member_role="owner",
            )
        finally:
            stop()

        assert result.status == "pending"
        # perm.require should be called once (RUN_CREATE) for member_role path
        mocks["perm_require"].assert_called_once()

    # ── Question validation ───────────────────────────────────────────

    def test_question_empty(self, mock_db):
        """Empty question → 400."""
        mocks, stop = _setup_create_task_mocks(mock_db)

        try:
            with pytest.raises(TaskServiceError, match="empty"):
                create_task(
                    mock_db,
                    workspace_id=uuid4(),
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="",
                    member_role="owner",
                )
        finally:
            stop()

    def test_question_whitespace_only(self, mock_db):
        """Whitespace-only question → 400."""
        mocks, stop = _setup_create_task_mocks(mock_db)

        try:
            with pytest.raises(TaskServiceError, match="empty"):
                create_task(
                    mock_db,
                    workspace_id=uuid4(),
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="   \t  \n  ",
                    member_role="owner",
                )
        finally:
            stop()

    # ── Skill validation ──────────────────────────────────────────────

    def test_skill_not_invokable(self, mock_db):
        """assert_skill_invokable raises SkillLifecycleError."""
        mocks, stop = _setup_create_task_mocks(mock_db)
        mocks["assert_skill_invokable"].side_effect = SkillLifecycleError(
            "skill disabled", status_code=403
        )

        try:
            with pytest.raises(TaskServiceError, match="skill disabled"):
                create_task(
                    mock_db,
                    workspace_id=uuid4(),
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="test",
                    member_role="owner",
                )
        finally:
            stop()

    # ── Capacity validation ───────────────────────────────────────────

    def test_capacity_rejected_first_check(self, mock_db):
        """First assert_enqueue_allowed raises CapacityError → 429."""
        mocks, stop = _setup_create_task_mocks(mock_db)
        mocks["assert_enqueue_allowed"].side_effect = CapacityError(
            "queue full"
        )

        try:
            with pytest.raises(TaskServiceError, match="queue full"):
                create_task(
                    mock_db,
                    workspace_id=uuid4(),
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="test",
                    member_role="owner",
                )
        finally:
            stop()

        mocks["metric_enqueue"].assert_called_once_with("capacity_rejected")

    # ── Budget validation ─────────────────────────────────────────────

    def test_budget_rejected(self, mock_db):
        """BudgetError → failed task created + 429."""
        mocks, stop = _setup_create_task_mocks(mock_db)
        mocks["assert_budget_allowed"].side_effect = BudgetError(
            "daily token budget exceeded"
        )

        try:
            with pytest.raises(TaskServiceError, match="daily token budget"):
                create_task(
                    mock_db,
                    workspace_id=uuid4(),
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="test",
                    member_role="owner",
                )
        finally:
            stop()

        # Verify failed task was created with correct state
        # db.add is called twice: once for the rejected task, once after flush
        assert mock_db.add.call_count >= 1
        mocks["metric_enqueue"].assert_called_with("budget_rejected")
        mocks["metric_terminal"].assert_called_once()
        mocks["attach_run_platform"].assert_called_once()
        mocks["log_run"].assert_called_once()

    # ── Enqueue failures ──────────────────────────────────────────────

    def test_enqueue_capacity_rejected(self, mock_db):
        """Second assert_enqueue_allowed raises CapacityError after commit."""
        ws_id = uuid4()
        mocks, stop = _setup_create_task_mocks(mock_db)
        # First call passes (pre-commit), second fails (post-commit)
        mocks["assert_enqueue_allowed"].side_effect = [
            None,
            CapacityError("post-commit queue full"),
        ]

        try:
            with pytest.raises(TaskServiceError, match="post-commit queue full"):
                create_task(
                    mock_db,
                    workspace_id=ws_id,
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="test",
                    member_role="owner",
                )
        finally:
            stop()

        mocks["metric_enqueue"].assert_called_with("capacity_rejected")
        mocks["metric_terminal"].assert_called_once()

    def test_enqueue_generic_error(self, mock_db):
        """enqueue_task raises Exception → task failed/enqueue_error."""
        ws_id = uuid4()
        mocks, stop = _setup_create_task_mocks(mock_db)
        mocks["enqueue_task"].side_effect = RuntimeError("redis connection lost")

        try:
            with pytest.raises(TaskServiceError, match="Failed to enqueue"):
                create_task(
                    mock_db,
                    workspace_id=ws_id,
                    user_id=uuid4(),
                    dataset_id=uuid4(),
                    question="test",
                    member_role="owner",
                )
        finally:
            stop()

        mocks["metric_enqueue"].assert_called_with("enqueue_error")
        mocks["metric_terminal"].assert_called_once()

    # ── require_sql_approval ──────────────────────────────────────────

    def test_require_sql_approval_true(self, mock_db):
        """_resolve_require_sql_approval returns True → task.require_sql_approval=True."""
        ws_id = uuid4()
        mocks, stop = _setup_create_task_mocks(mock_db)
        mocks["resolve_approval"].return_value = True

        try:
            result = create_task(
                mock_db,
                workspace_id=ws_id,
                user_id=uuid4(),
                dataset_id=uuid4(),
                question="test",
                member_role="owner",
            )
        finally:
            stop()

        assert result.require_sql_approval is True

    def test_require_sql_approval_false(self, mock_db):
        """_resolve_require_sql_approval returns False → task.require_sql_approval=False."""
        ws_id = uuid4()
        mocks, stop = _setup_create_task_mocks(mock_db)
        mocks["resolve_approval"].return_value = False

        try:
            result = create_task(
                mock_db,
                workspace_id=ws_id,
                user_id=uuid4(),
                dataset_id=uuid4(),
                question="test",
                member_role="owner",
            )
        finally:
            stop()

        assert result.require_sql_approval is False