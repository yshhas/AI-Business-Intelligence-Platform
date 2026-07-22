"""Idempotency-Key helper for task create (Wave 3 MVP) — Redis-backed.

Stabilization: fail-closed in production/staging; SET NX claim reduces double-enqueue races.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.core.config import get_settings
from app.services.queue import get_redis

logger = logging.getLogger("app.idempotency")

_TTL_SECONDS = 24 * 3600
_PENDING = "__pending__"


class IdempotencyError(Exception):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


def _key(workspace_id: UUID, user_id: UUID, idem_key: str) -> str:
    return f"aibi:idem:task:{workspace_id}:{user_id}:{idem_key.strip()}"


def _fail_closed() -> bool:
    return get_settings().is_hardened_env()


def lookup_task_id(
    *, workspace_id: UUID, user_id: UUID, idem_key: str
) -> UUID | None:
    """Return existing task id, or None if key free / pending claim in progress."""
    if not idem_key or not idem_key.strip():
        return None
    try:
        raw = get_redis().get(_key(workspace_id, user_id, idem_key))
        if not raw:
            return None
        text = raw.decode() if isinstance(raw, bytes) else str(raw)
        if text == _PENDING:
            raise IdempotencyError(
                "Idempotent request already in progress", status_code=409
            )
        return UUID(text)
    except IdempotencyError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("idempotency_lookup_failed", exc_info=True)
        if _fail_closed():
            raise IdempotencyError(
                f"Idempotency store unavailable: {exc}", status_code=503
            ) from exc
        return None


def claim_idempotency_key(
    *, workspace_id: UUID, user_id: UUID, idem_key: str
) -> UUID | None:
    """SET NX pending marker. Returns existing task UUID if key already finalized."""
    if not idem_key or not idem_key.strip():
        return None
    key = _key(workspace_id, user_id, idem_key)
    try:
        client = get_redis()
        created = bool(client.set(key, _PENDING, nx=True, ex=_TTL_SECONDS))
        if created:
            return None
        raw = client.get(key)
        text = (raw.decode() if isinstance(raw, bytes) else str(raw)) if raw else ""
        if text == _PENDING:
            raise IdempotencyError(
                "Idempotent request already in progress", status_code=409
            )
        if text:
            return UUID(text)
        # Race: key vanished — retry claim once
        if client.set(key, _PENDING, nx=True, ex=_TTL_SECONDS):
            return None
        raise IdempotencyError(
            "Idempotent request already in progress", status_code=409
        )
    except IdempotencyError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("idempotency_claim_failed", exc_info=True)
        if _fail_closed():
            raise IdempotencyError(
                f"Idempotency store unavailable: {exc}", status_code=503
            ) from exc
        return None


def remember_task_id(
    *, workspace_id: UUID, user_id: UUID, idem_key: str, task_id: UUID
) -> None:
    if not idem_key or not idem_key.strip():
        return
    try:
        get_redis().setex(
            _key(workspace_id, user_id, idem_key),
            _TTL_SECONDS,
            str(task_id),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("idempotency_store_failed", exc_info=True)
        if _fail_closed():
            raise IdempotencyError(
                f"Idempotency store unavailable: {exc}", status_code=503
            ) from exc


def release_claim(*, workspace_id: UUID, user_id: UUID, idem_key: str) -> None:
    """Drop pending marker if create failed before remember."""
    if not idem_key or not idem_key.strip():
        return
    try:
        key = _key(workspace_id, user_id, idem_key)
        client = get_redis()
        raw = client.get(key)
        text = (raw.decode() if isinstance(raw, bytes) else str(raw)) if raw else ""
        if text == _PENDING:
            client.delete(key)
    except Exception:  # noqa: BLE001
        logger.warning("idempotency_release_failed", exc_info=True)
