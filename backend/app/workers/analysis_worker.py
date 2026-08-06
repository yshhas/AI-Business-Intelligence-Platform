"""Analysis worker — Run lifecycle: claim, timeout, cooperative cancel (M2)."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from app.core.config import assert_boot_runtime, get_settings
from app.core.db import SessionLocal
from app.core.observability import configure_worker_logging, log_run
from app.core.repo_path import ensure_repo_root_on_path
from app.models import AnalysisTask
from app.services import artifact_service
from app.services import cost_budget
from app.services import queue as task_queue
from app.services import result_payload
from app.services import run_lifecycle as rl
from app.services import runtime_essentials as rt
from app.workers.run_control import CancelToken

ensure_repo_root_on_path()

from app.workers.agent_runtime import AgentAnalysisError, run_agent_analysis  # noqa: E402
from app.workers.mock_runtime import run_mock_analysis  # noqa: E402

logger = logging.getLogger(__name__)

# After abort, brief yield so in-flight checkpoints can observe the token (do not wait out Skill).
_ABORT_GRACE_SECONDS = 0.25


def _hitl_platform(task: AnalysisTask) -> dict[str, Any]:
    platform = (task.result_json or {}).get("platform") if isinstance(task.result_json, dict) else {}
    hitl = (platform or {}).get("hitl") if isinstance(platform, dict) else {}
    return hitl if isinstance(hitl, dict) else {}


def _is_hitl_execute_phase(task: AnalysisTask) -> bool:
    hitl = _hitl_platform(task)
    return hitl.get("phase") == "execute" and hitl.get("decision") == "approved"


def _should_park_hitl(task: AnalysisTask, settings) -> bool:
    """Park only on first plan pass — never re-park after HITL execute phase."""
    if _is_hitl_execute_phase(task):
        return False
    skill = (task.skill_id or "data.bi").strip() or "data.bi"
    return bool(
        settings.hitl_sql_approval_enabled
        and task.require_sql_approval
        and skill == "data.bi"
    )


def _verify_hitl_sql_snapshot(task: AnalysisTask):
    """H2-L7 / T5: fail-closed snapshot verify (shared agent.hitl_snapshot)."""
    from agent.hitl_snapshot import verify_sql_snapshot

    return verify_sql_snapshot(task.result_json if isinstance(task.result_json, dict) else {})


def _mark_hitl_snapshot_failed(db, task: AnalysisTask, verify_result) -> None:
    """Terminalize running HITL execute on snapshot failure; record Trace reason."""
    from agent.hitl_snapshot import snapshot_check_payload
    from app.models import AgentRunStep

    now = datetime.now(UTC)
    message = verify_result.message
    task.status = "failed"
    task.failure_class = rl.FAILURE_HITL_SNAPSHOT
    task.error_message = message[:2000]
    task.finished_at = now
    base = dict(task.result_json or {})
    lims = list(base.get("limitations") or [])
    note = f"HITL: snapshot check failed — {message}"
    if note not in lims:
        lims.append(note)
    base["limitations"] = lims
    platform = dict(base.get("platform") or {})
    hitl = dict(platform.get("hitl") or {})
    hitl.update(
        {
            "required": True,
            "phase": "execute",
            "decision": "approved",
            "executed": False,
            "execute_error": message[:500],
            "snapshot_check": snapshot_check_payload(verify_result),
        }
    )
    platform["hitl"] = hitl
    base["platform"] = platform
    task.result_json = rl.attach_run_platform(
        base,
        status="failed",
        failure_class=rl.FAILURE_HITL_SNAPSHOT,
        cancel_requested=bool(task.cancel_requested),
        timeout_seconds=task.timeout_seconds,
        task_id=str(task.id),
    )
    rl.apply_trace_columns(task, task.result_json)
    # Observable Trace step (not Skill-generated)
    db.add(
        AgentRunStep(
            task_id=task.id,
            step_no=_next_step_no(db, task.id),
            node_name="hitl_snapshot_check",
            status="error",
            input_json={"phase": "execute"},
            output_json=snapshot_check_payload(verify_result),
            error_message=message[:2000],
            latency_ms=0,
        )
    )
    db.add(task)
    db.commit()
    _observe_terminal(task)
    log_run(
        logger,
        logging.INFO,
        f"hitl_snapshot failed: {verify_result.reason_code} {message}",
        run_id=task.id,
        status="failed",
        failure_class=rl.FAILURE_HITL_SNAPSHOT,
        skill_id=task.skill_id,
    )


def _next_step_no(db, task_id: UUID) -> int:
    from sqlalchemy import func, select
    from app.models import AgentRunStep

    n = db.scalar(
        select(func.coalesce(func.max(AgentRunStep.step_no), 0)).where(
            AgentRunStep.task_id == task_id
        )
    )
    return int(n or 0) + 1


def _mark_awaiting_approval(db, task: AnalysisTask, result_json: dict[str, Any] | None) -> None:
    """HITL H1: park after plan — fence closed via status≠running."""
    from agent.hitl_snapshot import attach_snapshot_on_park

    now = datetime.now(UTC)
    base = attach_snapshot_on_park(result_json)
    platform = dict(base.get("platform") or {})
    hitl = dict(platform.get("hitl") or {})
    hitl["phase"] = "awaiting"
    hitl["required"] = True
    platform["hitl"] = hitl
    base["platform"] = platform
    task.status = rl.STATUS_AWAITING_APPROVAL
    task.failure_class = None
    task.error_message = None
    task.finished_at = None
    task.approval_requested_at = now
    task.result_json = rl.attach_run_platform(
        base,
        status=rl.STATUS_AWAITING_APPROVAL,
        failure_class=None,
        cancel_requested=bool(task.cancel_requested),
        timeout_seconds=task.timeout_seconds,
        task_id=str(task.id),
    )
    # Soft seal for Trace columns without treating as terminal success
    rl.apply_trace_columns(task, task.result_json)
    db.add(task)
    db.commit()
    log_run(
        logger,
        logging.INFO,
        "awaiting_approval (HITL plan parked)",
        run_id=task.id,
        status=rl.STATUS_AWAITING_APPROVAL,
        skill_id=task.skill_id,
    )


def _finalize_tokens(db, task: AnalysisTask) -> None:
    """P0-2: denormalize step LLM usage onto task.llm_total_tokens (soft budget index)."""
    try:
        cost_budget.apply_llm_total_tokens(db, task)
    except Exception:  # noqa: BLE001
        logger.exception("llm_total_tokens aggregate failed for %s", task.id)


def _list_hitl_resume_recovery_ids(db) -> list[UUID]:
    """DB recovery for Worker restart: awaiting + resume flag (Redis wake may be lost)."""
    stmt = select(AnalysisTask.id).where(
        AnalysisTask.status == rl.STATUS_AWAITING_APPROVAL,
        AnalysisTask.hitl_resume_requested.is_(True),
    )
    return list(db.scalars(stmt).all())


def recover_pending_hitl_resumes() -> int:
    """Process durable hitl_resume_requested rows (H2 restart recovery). Returns CAS wins."""
    db = SessionLocal()
    try:
        ids = _list_hitl_resume_recovery_ids(db)
    finally:
        db.close()
    won = 0
    for task_id in ids:
        if process_hitl_resume(task_id):
            won += 1
    return won


def process_hitl_resume(task_id: UUID) -> bool:
    """HITL H2: CAS awaiting→running (phase=execute), then execute-only via process_task.

    Returns True iff CAS won (execute may still fail-closed to failed).
    """
    db = SessionLocal()
    cas_won = False
    try:
        try:
            rt.reclaim_stale_running(db, get_settings())
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("stale reclaim failed (hitl resume)")
        try:
            rt.expire_awaiting_approval(db, get_settings())
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("awaiting_approval expire failed (hitl resume)")

        task = db.get(AnalysisTask, task_id)
        if task is None:
            logger.warning("HITL resume task %s not found — skip", task_id)
            return False

        if task.status in rl.TERMINAL_STATUSES:
            logger.info(
                "HITL resume %s already terminal status=%s — skip",
                task_id,
                task.status,
            )
            return False

        if task.status != rl.STATUS_AWAITING_APPROVAL:
            # Dual resume / already claimed: running or other active → no-op
            logger.info(
                "HITL resume %s status=%s — skip (CAS not awaiting)",
                task_id,
                task.status,
            )
            return False

        if not task.hitl_resume_requested:
            logger.info(
                "HITL resume %s awaiting but hitl_resume_requested=false — skip",
                task_id,
            )
            return False

        now = datetime.now(UTC)
        # H2-L3/L5: only one resume wins; reject/cancel/timeout lose the race here
        result = db.execute(
            update(AnalysisTask)
            .where(
                AnalysisTask.id == task_id,
                AnalysisTask.status == rl.STATUS_AWAITING_APPROVAL,
                AnalysisTask.hitl_resume_requested.is_(True),
            )
            .values(
                status="running",
                hitl_resume_requested=False,
                last_heartbeat_at=now,
                # Keep started_at (plan wall-clock); clear cooperative cancel latch if any
                cancel_requested=False,
                error_message=None,
                failure_class=None,
                finished_at=None,
            )
        )
        db.commit()
        if result.rowcount == 0:
            db.refresh(task)
            logger.info(
                "HITL resume CAS lost for %s status=%s resume=%s",
                task_id,
                task.status,
                task.hitl_resume_requested,
            )
            return False

        db.refresh(task)
        base = dict(task.result_json or {})
        platform = dict(base.get("platform") or {})
        hitl = dict(platform.get("hitl") or {})
        hitl.update(
            {
                "required": True,
                "phase": "execute",
                "decision": "approved",
                "resume_requested": False,
            }
        )
        platform["hitl"] = hitl
        base["platform"] = platform
        task.result_json = rl.attach_run_platform(
            base,
            status="running",
            failure_class=None,
            cancel_requested=False,
            timeout_seconds=task.timeout_seconds,
            task_id=str(task.id),
        )
        rl.apply_trace_columns(task, task.result_json)
        db.add(task)
        db.commit()
        cas_won = True
        log_run(
            logger,
            logging.INFO,
            "hitl_resume CAS → running (phase=execute)",
            run_id=task_id,
            status="running",
            skill_id=task.skill_id,
        )
    finally:
        db.close()

    if cas_won:
        # T3: continue on running path (snapshot check + execute-only inside process_task)
        process_task(task_id)
    return cas_won


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
        try:
            rt.expire_awaiting_approval(db, settings)
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("awaiting_approval expire failed")

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

        # HITL H2 T5: fail-closed snapshot check before any Skill / Plane work
        if _is_hitl_execute_phase(task):
            snap = _verify_hitl_sql_snapshot(task)
            if not snap.ok:
                _mark_hitl_snapshot_failed(db, task, snap)
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
                _seal_result_json(db, task)
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
                _seal_result_json(db, task)
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
                # Trace columns applied inside cancel marker after attach
            _mark_cancelled(db, task, "Run cancelled")
            return

        if _should_park_hitl(task, settings):
            _mark_awaiting_approval(db, task, result_json)
            return

        task.result_json = rl.attach_run_platform(
            result_json,
            status="succeeded",
            failure_class=None,
            cancel_requested=False,
            timeout_seconds=task.timeout_seconds,
            task_id=str(task.id),
        )
        _seal_result_json(db, task)
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
    _seal_result_json(db, task)
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
    _seal_result_json(db, task)
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


def _seal_result_json(db, task: AnalysisTask) -> None:
    """Trace columns → artifacts from full payload → P1.4 hot slim."""
    rl.apply_trace_columns(task, task.result_json)
    _materialize_artifacts(db, task)
    task.result_json = result_payload.slim_for_persist(task.result_json)


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
            f"hitl_resume_queue={settings.hitl_resume_queue_key} "
            f"timeout={settings.run_timeout_seconds}s max_inflight={settings.run_max_in_flight} "
            f"queue_max_depth={settings.analysis_queue_max_depth}"
        ),
        status="worker_boot",
    )
    if not task_queue.ping():
        raise SystemExit("Redis PING failed — start aibi-redis first")

    # Boot recovery: durable resume flags if Redis wake was lost
    try:
        n = recover_pending_hitl_resumes()
        if n:
            logger.info("Boot recovered %s HITL resume Run(s)", n)
    except Exception:  # noqa: BLE001
        logger.exception("boot HITL resume recovery failed")

    while True:
        work = task_queue.blocking_dequeue_work()
        if work is None:
            db = SessionLocal()
            try:
                rt.reclaim_stale_running(db, settings)
                rt.expire_awaiting_approval(db, settings)
            except Exception:  # noqa: BLE001
                db.rollback()
                logger.exception("idle reclaim/expire failed")
            finally:
                db.close()
            # Redis wake lost / Worker restart: pick up awaiting + resume flag
            try:
                recover_pending_hitl_resumes()
            except Exception:  # noqa: BLE001
                logger.exception("idle HITL resume recovery failed")
            continue
        kind, task_id = work
        if kind == "hitl_resume":
            process_hitl_resume(task_id)
        else:
            process_task(task_id)
        time.sleep(0.05)


if __name__ == "__main__":
    run_forever()
