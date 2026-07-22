"""Redis sliding-window rate limits (P0 Trust)."""

from __future__ import annotations

import logging
from uuid import UUID

from app.core.config import get_settings
from app.services.queue import get_redis

logger = logging.getLogger("app.rate_limit")


class RateLimitExceeded(Exception):
    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message)
        self.status_code = 429


def _hit(key: str, *, limit: int, window_seconds: int = 60) -> None:
    settings = get_settings()
    if not settings.rate_limit_enabled or limit <= 0:
        return
    redis_key = f"aibi:rl:{key}"
    try:
        client = get_redis()
        count = int(client.incr(redis_key))
        if count == 1:
            client.expire(redis_key, window_seconds)
        if count > limit:
            raise RateLimitExceeded(
                f"Rate limit exceeded ({limit} requests per {window_seconds}s)"
            )
    except RateLimitExceeded:
        raise
    except Exception:  # noqa: BLE001 — fail open locally; fail closed in prod/staging
        logger.warning("rate_limit_redis_error key=%s", key, exc_info=True)
        if settings.is_hardened_env():
            raise RateLimitExceeded(
                "Rate limit unavailable (Redis error); refusing request in hardened env"
            ) from None


def check_auth_rate_limit(*, client_key: str) -> None:
    settings = get_settings()
    try:
        _hit(
            f"auth:{client_key}",
            limit=settings.rate_limit_auth_per_minute,
            window_seconds=60,
        )
    except RateLimitExceeded:
        try:
            from app.core.metrics import observe_rate_limit

            observe_rate_limit("auth")
        except Exception:  # noqa: BLE001
            pass
        raise


def check_task_create_rate_limit(*, user_id: UUID, workspace_id: UUID) -> None:
    settings = get_settings()
    try:
        _hit(
            f"task_create:{user_id}:{workspace_id}",
            limit=settings.rate_limit_task_create_per_minute,
            window_seconds=60,
        )
    except RateLimitExceeded:
        try:
            from app.core.metrics import observe_rate_limit

            observe_rate_limit("task_create")
        except Exception:  # noqa: BLE001
            pass
        raise
