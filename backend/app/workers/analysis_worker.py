"""Analysis worker — Run lifecycle: claim, timeout, cooperative cancel (M2)."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import update

from app.core.config import assert_boot_runtime, get_settings
from app.core.db import SessionLocal
from app.core.observability import configure_worker_logging, log_run
from app.core.repo_path import ensure_repo_root_on_path
from app.models import AnalysisTask
from app.services import artifact_service
from app.services import cost_budget
from app.services import queue as task_queue
from app.services import run_lifecycle as rl
from app.services import runtime_essentials as rt
from app.workers.run_control import CancelToken

ensure_repo_root_on_path()

from app.workers.agent_runtime import AgentAnalysisError, run_agent_analysis  # noqa: E402
from app.workers.mock_runtime import run_mock_analysis  # noqa: E402

logger = logging.getLogger(__name__)

# After abort, brief yield so in-flight checkpoints can observe the token (do not wait out Skill).
_ABORT_GRACE_SECONDS = 0.25


def _finalize_tokens(db, task: AnalysisTask) -> None:
    """P0-2: denormalize step LLM usage onto task.llm_total_tokens (soft budget index)."""
    try:
        cost_budget.apply_llm_total_tokens(db, task)
    except Exception:  # noqa: BLE001
        logger.exception("llm_total_tokens aggregate failed for %s", task.id)


def process_task(task_id: UUID) -> None:
    settings = get_settings()
    runtime = settings.analysis_runtime.strip().lower()
    if runtime not in {"mock", "agent"}:
        raise RuntimeError(
            f"Unsupported ANALYSIS_RUNTIME={settings.analysis_runtime!r}. "
            "Allowed: mock | agent"
        )

    db = SessionLocal()
    try:
        # E3: reclaim orphans before taking more work
        try:
            rt.reclaim_stale_running(db, settings)
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("stale reclaim failed")

        task = db.get(AnalysisTask, task_id)
        if task is None:
            logger.warning("Task %s not found — skip", task_id)
            return

        if task.status in rl.TERMINAL_STATUSES:
            logger.info("Task %s already terminal status=%s — skip", task_id, task.status)
            return

        # Pending cancel before claim
        if task.status == "pending" and task.cancel_requested:
            _mark_cancelled(db, task, "Run cancelled before start")
            return

        if task.status == "pending":
            if not rt.claim_allowed(db, settings):
                # Already BRPOP'd — put back and defer
                task_queue.requeue_task(task_id)
                logger.info(
                    "Task %s deferred — in-flight capacity (running>=%s)",
                    task_id,
                    settings.run_max_in_flight,
                )
                time.sleep(0.25)
                return

            now = datetime.now(UTC)
            # CAS-style claim: only pending → running
            result = db.execute(
                update(AnalysisTask)
                .where(
                    AnalysisTask.id == task_id,
                    AnalysisTask.status == "pending",
                    AnalysisTask.cancel_requested.is_(False),
                )
                .values(
                    status="running",
                    started_at=now,
                    last_heartbeat_at=now,
                    error_message=None,
                    failure_class=None,
                )
            )
            db.commit()
            if result.rowcount == 0:
                db.refresh(task)
                logger.info(
                    "Task %s claim skipped status=%s cancel=%s",
                    task_id,
                    task.status,
                    task.cancel_requested,
                )
                return
            db.refresh(task)

        if task.status != "running":
            logger.info("Task %s status=%s — skip", task_id, task.status)
            return

        if task.cancel_requested:
            _mark_cancelled(db, task, "Run cancelled")
            return

        timeout = int(task.timeout_seconds or settings.run_timeout_seconds or 120)

        try:
            result_json = _run_with_timeout(
                db, task, runtime=runtime, timeout_seconds=timeout
            )
        except _Cancelled:
            task = db.get(AnalysisTask, task_id)
            if task is not None:
                _mark_cancelled(db, task, "Run cancelled during execution")
            return
        except _TimedOut:
            task = db.get(AnalysisTask, task_id)
            if task is not None:
                _mark_timed_out(db, task, timeout)
            return
        except AgentAnalysisError as exc:
            try:
                task = db.get(AnalysisTask, task_id)
                if task is None:
                    return
                if task.status in rl.TERMINAL_STATUSES:
                    return
                partial = dict(exc.result_json or {})
                task.status = "failed"
                task.failure_class = rl.classify_exception(exc)
                task.error_message = str(exc)
                task.finished_at = datetime.now(UTC)
                task.result_json = rl.attach_run_platform(
                    partial,
                    status="failed",
                    failure_class=task.failure_class,
                    cancel_requested=bool(task.cancel_requested),
                    timeout_seconds=task.timeout_seconds,
                    task_id=str(task.id),
                )
                rl.apply_trace_columns(task, task.result_json)
                _materialize_artifacts(db, task)
                _finalize_tokens(db, task)
                db.add(task)
                db.commit()
                _observe_terminal(task)
                log_run(
                    logger,
                    logging.INFO,
                    f"agent failed: {exc}",
                    run_id=task_id,
                    status="failed",
                    failure_class=task.failure_class,
                    skill_id=task.skill_id,
                )
            except Exception:  # noqa: BLE001
                db.rollback()
                logger.exception("Could not persist agent failure for %s", task_id)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Task %s failed", task_id)
            try:
                task = db.get(AnalysisTask, task_id)
                if task is None:
                    return
                # Do not overwrite terminal cancel/timeout if somehow set
                if task.status in rl.TERMINAL_STATUSES:
                    return
                task.status = "failed"
                task.failure_class = rl.classify_exception(exc)
                task.error_message = str(exc)
                task.finished_at = datetime.now(UTC)
                task.result_json = rl.attach_run_platform(
                    task.result_json,
                    status="failed",
                    failure_class=task.failure_class,
                    cancel_requested=bool(task.cancel_requested),
                    timeout_seconds=task.timeout_seconds,
                    task_id=str(task.id),
                )
                rl.apply_trace_columns(task, task.result_json)
                _materialize_artifacts(db, task)
                _finalize_tokens(db, task)
                db.add(task)
                db.commit()
                _observe_terminal(task)
                log_run(
                    logger,
                    logging.INFO,
                    f"failed: {exc}",
                    run_id=task_id,
                    status="failed",
                    failure_class=task.failure_class,
                    skill_id=task.skill_id,
                )
            except Exception:  # noqa: BLE001
                db.rollback()
                logger.exception("Could not persist failure state for %s", task_id)
            return

        # Success path — re-check cancel/timeout before committing success
        task = db.get(AnalysisTask, task_id)
        if task is None:
            return
        # Discard late success if already terminalized (cooperative abort race)
        if task.status in rl.TERMINAL_STATUSES:
            logger.info(
                "Task %s already terminal after run (status=%s) — discard success write",
                task_id,
                task.status,
            )
            return
        if task.cancel_requested or task.status == "cancelled":
            # Preserve best-effort execution from completed work if present
            if result_json:
                base = dict(result_json)
                task.result_json = base
                rl.apply_trace_columns(task, base)
            _mark_cancelled(db, task, "Run cancelled")
            return

        task.result_json = rl.attach_run_platform(
            result_json,
            status="succeeded",
            failure_class=None,
            cancel_requested=False,
            timeout_seconds=task.timeout_seconds,
            task_id=str(task.id),
        )
        rl.apply_trace_columns(task, task.result_json)
        _materialize_artifacts(db, task)
        _finalize_tokens(db, task)
        task.status = "succeeded"
        task.failure_class = None
        task.finished_at = datetime.now(UTC)
        task.error_message = None
        db.add(task)
        db.commit()
        _observe_terminal(task)
        log_run(
            logger,
            logging.INFO,
            f"succeeded (runtime={runtime})",
            run_id=task_id,
            status="succeeded",
            skill_id=task.skill_id,
        )
    finally:
        db.close()


class _TimedOut(Exception):
    pass


class _Cancelled(Exception):
    pass


def _run_with_timeout(
    db,
    task: AnalysisTask,
    *,
    runtime: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run Skill in a worker thread with wall-clock abort (cooperative checkpoints)."""
    task_id = task.id
    token = CancelToken()

    def _work() -> dict[str, Any]:
        from agent.run_control import RunAborted

        # Fresh session inside thread for SQLAlchemy safety
        thread_db = SessionLocal()
        try:
            t = thread_db.get(AnalysisTask, task_id)
            if t is None:
                raise RuntimeError("Task disappeared")
            token.raise_if_aborted()
            if t.cancel_requested:
                token.request_cancel()
                raise RunAborted("cancelled")
            if runtime == "mock":
                result = run_mock_analysis(
                    thread_db,
                    t,
                    cancel_check=token.raise_if_aborted,
                    token=token,
                )
            else:
                settings = get_settings()
                try:
                    result = run_agent_analysis(
                        thread_db,
                        t,
                        settings,
                        cancel_check=token.raise_if_aborted,
                        token=token,
                    )
                except AgentAnalysisError:
                    # Persist AgentRunStep rows even when Skill fails (if still running)
                    thread_db.commit()
                    raise
            thread_db.commit()
            return result
        except RunAborted as exc:
            thread_db.rollback()
            if exc.reason == "timeout":
                raise _TimedOut() from exc
            raise _Cancelled() from exc
        except (_Cancelled, _TimedOut, AgentAnalysisError):
            raise
        except Exception:
            thread_db.rollback()
            raise
        finally:
            thread_db.close()

    pool = ThreadPoolExecutor(max_workers=1)
    fut = pool.submit(_work)
    aborted: str | None = None
    try:
        deadline = time.monotonic() + max(1, timeout_seconds)
        settings = get_settings()
        hb_every = int(settings.run_heartbeat_interval_seconds or 0)
        last_hb = time.monotonic()
        while True:
            # Prefer timeout decision even if the worker thread is about to finish.
            if time.monotonic() >= deadline:
                token.request_timeout()
                aborted = "timeout"
                break
            wait = min(0.25, max(0.05, deadline - time.monotonic()))
            try:
                return fut.result(timeout=wait)
            except FuturesTimeout:
                db.expire_all()
                fresh = db.get(AnalysisTask, task_id)
                if fresh is not None and fresh.cancel_requested:
                    token.request_cancel()
                    aborted = "cancelled"
                    break
                if hb_every > 0 and (time.monotonic() - last_hb) >= hb_every:
                    try:
                        rt.touch_heartbeat(db, task_id)
                        last_hb = time.monotonic()
                    except Exception:  # noqa: BLE001
                        db.rollback()
                        logger.exception("heartbeat failed for %s", task_id)
                continue
            except _Cancelled:
                aborted = "cancelled"
                raise
            except _TimedOut:
                aborted = "timeout"
                raise
    finally:
        if aborted:
            token.close()
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                # Python < 3.9
                pool.shutdown(wait=False)
            # Brief yield only — do not join the Skill thread (wall-clock abort).
            time.sleep(_ABORT_GRACE_SECONDS)
            if not fut.done():
                logger.warning(
                    "Task %s Skill thread still running after abort (writes fenced)",
                    task_id,
                )
        else:
            pool.shutdown(wait=True)

    if aborted == "timeout":
        raise _TimedOut()
    if aborted == "cancelled":
        raise _Cancelled()
    raise RuntimeError("unreachable: _run_with_timeout without result or abort")


def _mark_cancelled(db, task: AnalysisTask, message: str) -> None:
    if task.status in rl.TERMINAL_STATUSES and task.status != "running":
        if task.status == "cancelled":
            return
    task.cancel_requested = True
    task.status = "cancelled"
    task.failure_class = rl.FAILURE_CANCELLED
    task.error_message = message
    task.finished_at = datetime.now(UTC)
    base = dict(task.result_json or {})
    lims = list(base.get("limitations") or [])
    for item in rl.CANCEL_LIMITATIONS:
        if item not in lims:
            lims.append(item)
    base["limitations"] = lims
    task.result_json = rl.attach_run_platform(
        base,
        status="cancelled",
        failure_class=rl.FAILURE_CANCELLED,
        cancel_requested=True,
        timeout_seconds=task.timeout_seconds,
        task_id=str(task.id),
    )
    rl.apply_trace_columns(task, task.result_json)
    _materialize_artifacts(db, task)
    _finalize_tokens(db, task)
    db.add(task)
    db.commit()
    _observe_terminal(task)
    log_run(
        logger,
        logging.INFO,
        message,
        run_id=task.id,
        status="cancelled",
        failure_class=rl.FAILURE_CANCELLED,
        skill_id=task.skill_id,
    )


def _mark_timed_out(db, task: AnalysisTask, timeout: int) -> None:
    if task.status in rl.TERMINAL_STATUSES:
        return
    task.status = "timed_out"
    task.failure_class = rl.FAILURE_TIMEOUT
    task.error_message = f"Run exceeded timeout of {timeout}s"
    task.finished_at = datetime.now(UTC)
    base = dict(task.result_json or {})
    lims = list(base.get("limitations") or [])
    for item in rl.TIMEOUT_LIMITATIONS:
        if item not in lims:
            lims.append(item)
    base["limitations"] = lims
    task.result_json = rl.attach_run_platform(
        base,
        status="timed_out",
        failure_class=rl.FAILURE_TIMEOUT,
        cancel_requested=bool(task.cancel_requested),
        timeout_seconds=task.timeout_seconds or timeout,
        task_id=str(task.id),
    )
    rl.apply_trace_columns(task, task.result_json)
    _materialize_artifacts(db, task)
    _finalize_tokens(db, task)
    db.add(task)
    db.commit()
    _observe_terminal(task)
    log_run(
        logger,
        logging.INFO,
        f"timed_out after {timeout}s",
        run_id=task.id,
        status="timed_out",
        failure_class=rl.FAILURE_TIMEOUT,
        skill_id=task.skill_id,
    )


def _materialize_artifacts(db, task: AnalysisTask) -> None:
    """M6: persist run_artifacts metadata + sync Trace ArtifactRefs (content_ref only)."""
    platform = dict((task.result_json or {}).get("platform") or {})
    skill_id = str(platform.get("skill_id") or task.skill_id or "data.bi")
    artifact_service.materialize_for_task(
        db, task, task.result_json, skill_id=skill_id
    )


def _observe_terminal(task: AnalysisTask) -> None:
    try:
        from app.core.metrics import observe_task_terminal

        observe_task_terminal(status=task.status, failure_class=task.failure_class)
    except Exception:  # noqa: BLE001
        pass


def run_forever() -> None:
    settings = get_settings()
    assert_boot_runtime(settings)
    runtime = settings.analysis_runtime.strip().lower()
    if runtime not in {"mock", "agent"}:
        raise SystemExit(
            f"Unsupported ANALYSIS_RUNTIME={settings.analysis_runtime!r}. "
            "Allowed: mock | agent"
        )
    configure_worker_logging(
        log_format=settings.log_format,
        log_level=settings.log_level,
    )
    try:
        from app.services import skill_lifecycle as skills

        skills.sync_from_settings(settings)
    except Exception:  # noqa: BLE001
        logger.exception("skill lifecycle sync failed at worker boot")
    try:
        from app.workers.health_server import start_worker_health_server

        start_worker_health_server(
            host=settings.worker_health_host,
            port=int(settings.worker_health_port),
        )
    except Exception:  # noqa: BLE001
        logger.exception("worker health server failed to start")
    log_run(
        logger,
        logging.INFO,
        (
            f"Worker starting runtime={runtime} queue={settings.analysis_queue_key} "
            f"timeout={settings.run_timeout_seconds}s max_inflight={settings.run_max_in_flight} "
            f"queue_max_depth={settings.analysis_queue_max_depth}"
        ),
        status="worker_boot",
    )
    if not task_queue.ping():
        raise SystemExit("Redis PING failed — start aibi-redis first")

    while True:
        # Idle reclaim when BRPOP times out (no message)
        task_id = task_queue.blocking_dequeue()
        if task_id is None:
            db = SessionLocal()
            try:
                rt.reclaim_stale_running(db, settings)
            except Exception:  # noqa: BLE001
                db.rollback()
                logger.exception("idle stale reclaim failed")
            finally:
                db.close()
            continue
        process_task(task_id)
        time.sleep(0.05)


if __name__ == "__main__":
    run_forever()
