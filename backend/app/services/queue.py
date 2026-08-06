"""Redis List queue for analysis task IDs (no Celery)."""

from __future__ import annotations

from uuid import UUID

import redis

from app.core.config import get_settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def enqueue_task(task_id: UUID) -> None:
    settings = get_settings()
    get_redis().lpush(settings.analysis_queue_key, str(task_id))


def enqueue_hitl_resume(task_id: UUID) -> None:
    """Wake Worker for HITL Approve→Execute (H2-L6). Does not use the main analysis queue."""
    settings = get_settings()
    get_redis().lpush(settings.hitl_resume_queue_key, str(task_id))


def hitl_resume_queue_length() -> int:
    settings = get_settings()
    return int(get_redis().llen(settings.hitl_resume_queue_key) or 0)


def queue_length() -> int:
    settings = get_settings()
    return int(get_redis().llen(settings.analysis_queue_key) or 0)


def requeue_task(task_id: UUID) -> None:
    """Put task id back on the list (e.g. claim deferred due to in-flight cap)."""
    enqueue_task(task_id)


def blocking_dequeue(*, timeout_seconds: int | None = None) -> UUID | None:
    """BRPOP main analysis queue only; returns task_id or None on timeout."""
    settings = get_settings()
    timeout = (
        settings.redis_brpop_timeout_seconds if timeout_seconds is None else timeout_seconds
    )
    item = get_redis().brpop(settings.analysis_queue_key, timeout=timeout)
    if item is None:
        return None
    _key, raw = item
    return UUID(raw)


def blocking_dequeue_work(
    *, timeout_seconds: int | None = None
) -> tuple[str, UUID] | None:
    """BRPOP HITL resume queue (priority) then main analysis queue.

    Returns ``(\"hitl_resume\"|\"analysis\", task_id)`` or None on timeout.
    """
    settings = get_settings()
    timeout = (
        settings.redis_brpop_timeout_seconds if timeout_seconds is None else timeout_seconds
    )
    # Left-to-right: prefer resume so Approve→Execute is not starved by plan work.
    item = get_redis().brpop(
        [settings.hitl_resume_queue_key, settings.analysis_queue_key],
        timeout=timeout,
    )
    if item is None:
        return None
    key, raw = item
    kind = "hitl_resume" if key == settings.hitl_resume_queue_key else "analysis"
    return kind, UUID(raw)


def ping() -> bool:
    return get_redis().ping() is True
