"""E3 Runtime Essentials — capacity guards + stale running reclaim (Worker-owned)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import AnalysisTask
from app.services import artifact_service
from app.services import queue as task_queue
from app.services import run_lifecycle as rl

logger = logging.getLogger(__name__)


class CapacityError(Exception):
    """Enqueue rejected due to in-flight or queue depth (map to HTTP 429)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def count_running(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(AnalysisTask).where(
                AnalysisTask.status == "running"
            )
        )
        or 0
    )


def assert_enqueue_allowed(db: Session, settings: Settings | None = None) -> None:
    """Reject enqueue when queue is full or global in-flight is at capacity."""
    settings = settings or get_settings()
    max_depth = int(settings.analysis_queue_max_depth)
    max_inflight = int(settings.run_max_in_flight)

    depth = task_queue.queue_length()
    if depth >= max_depth:
        raise CapacityError(
            f"Analysis queue is full (depth={depth}, max={max_depth})"
        )

    running = count_running(db)
    if running >= max_inflight:
        raise CapacityError(
            f"Global in-flight Run capacity reached "
            f"(running={running}, max={max_inflight})"
        )


def claim_allowed(db: Session, settings: Settings | None = None) -> bool:
    """True if Worker may claim another pending Run into running."""
    settings = settings or get_settings()
    return count_running(db) < int(settings.run_max_in_flight)


def stale_cutoff(settings: Settings | None = None) -> datetime:
    settings = settings or get_settings()
    ttl = int(settings.stale_running_seconds)
    if ttl <= 0:
        # Default: timeout + grace (never shorter than run_timeout)
        ttl = max(int(settings.run_timeout_seconds) + 60, 180)
    return datetime.now(UTC) - timedelta(seconds=ttl)


def reclaim_stale_running(db: Session, settings: Settings | None = None) -> int:
    """Terminalize orphan `running` rows → failed + runtime_reclaimed.

    Staleness uses coalesce(last_heartbeat_at, started_at).
    Heartbeat is only a freshness signal — not a lease system.
    """
    settings = settings or get_settings()
    cutoff = stale_cutoff(settings)
    stmt = select(AnalysisTask).where(AnalysisTask.status == "running")
    tasks = list(db.scalars(stmt).all())
    reclaimed = 0
    for task in tasks:
        anchor = task.last_heartbeat_at or task.started_at
        if anchor is None:
            continue
        # Normalize aware comparison
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=UTC)
        if anchor > cutoff:
            continue
        _mark_reclaimed(db, task)
        reclaimed += 1
    if reclaimed:
        db.commit()
        logger.info("Reclaimed %s stale running Run(s)", reclaimed)
    return reclaimed


def touch_heartbeat(db: Session, task_id: UUID) -> None:
    """Best-effort heartbeat for stale detection (Worker-owned)."""
    db.execute(
        update(AnalysisTask)
        .where(
            AnalysisTask.id == task_id,
            AnalysisTask.status == "running",
        )
        .values(last_heartbeat_at=datetime.now(UTC))
    )
    db.commit()


def _mark_reclaimed(db: Session, task: AnalysisTask) -> None:
    task.status = "failed"
    task.failure_class = rl.FAILURE_RUNTIME_RECLAIMED
    task.error_message = (
        "Run reclaimed: Worker lost or heartbeat/started_at exceeded stale threshold"
    )
    task.finished_at = datetime.now(UTC)
    base = dict(task.result_json or {})
    lims = list(base.get("limitations") or [])
    note = (
        "Run reclaimed after Worker loss or stale heartbeat "
        "(cooperative runtime; in-flight work may not have aborted)."
    )
    if note not in lims:
        lims.append(note)
    base["limitations"] = lims
    task.result_json = rl.attach_run_platform(
        base,
        status="failed",
        failure_class=rl.FAILURE_RUNTIME_RECLAIMED,
        cancel_requested=bool(task.cancel_requested),
        timeout_seconds=task.timeout_seconds,
        task_id=str(task.id),
    )
    # Mark execution incomplete for Trace honesty
    platform = dict(task.result_json.get("platform") or {})
    execution = dict(platform.get("execution") or {})
    summary = dict(execution.get("summary") or {})
    summary["incomplete"] = True
    execution["summary"] = summary
    platform["execution"] = execution
    task.result_json = {**task.result_json, "platform": platform}
    rl.apply_trace_columns(task, task.result_json)
    try:
        artifact_service.materialize_for_task(
            db,
            task,
            task.result_json,
            skill_id=str(platform.get("skill_id") or task.skill_id or "data.bi"),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Artifact materialize failed during reclaim of %s", task.id)
    db.add(task)
