"""Trace-aligned structured logging helpers (DH.5 + T-08).

Logs correlate to Execution Trace — they do not replace platform.execution.
Adds request_id context + optional JSON log lines for operator join.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

REQUEST_ID_HEADER = "X-Request-ID"


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> Token:
    return _request_id.set(value or "-")


def reset_request_id(token: Token) -> None:
    _request_id.reset(token)


def new_request_id() -> str:
    return str(uuid4())


def run_fields(
    *,
    run_id: UUID | str | None = None,
    status: str | None = None,
    failure_class: str | None = None,
    skill_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "request_id": request_id if request_id is not None else get_request_id(),
        "run_id": str(run_id) if run_id is not None else "-",
        "status": status or "-",
        "failure_class": failure_class or "-",
        "skill_id": skill_id or "-",
    }


def log_run(
    logger: logging.Logger,
    level: int,
    msg: str,
    *,
    run_id: UUID | str | None = None,
    status: str | None = None,
    failure_class: str | None = None,
    skill_id: str | None = None,
    request_id: str | None = None,
    **kwargs: Any,
) -> None:
    """Emit a log line with request/run keys for operator grep / Trace join."""
    extra = run_fields(
        run_id=run_id,
        status=status,
        failure_class=failure_class,
        skill_id=skill_id,
        request_id=request_id,
    )
    if _json_log_enabled():
        # Fields live in JSON object; keep msg clean.
        logger.log(level, msg, extra=extra, **kwargs)
        return
    # Text mode: keep keys visible even with default formatters.
    prefix = (
        f"request_id={extra['request_id']} run_id={extra['run_id']} "
        f"status={extra['status']} failure_class={extra['failure_class']} "
        f"skill_id={extra['skill_id']}"
    )
    logger.log(level, "%s | %s", prefix, msg, extra=extra, **kwargs)


def _json_log_enabled() -> bool:
    try:
        from app.core.config import get_settings

        return get_settings().log_format.strip().lower() == "json"
    except Exception:  # noqa: BLE001
        return False


class ContextFieldsFilter(logging.Filter):
    """Ensure correlation fields exist on every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = get_request_id()
        for key in ("run_id", "status", "failure_class", "skill_id"):
            if not hasattr(record, key) or getattr(record, key) in (None, ""):
                setattr(record, key, "-")
        return True


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line — no ELK/OTel stack required."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "run_id": getattr(record, "run_id", "-"),
            "status": getattr(record, "status", "-"),
            "failure_class": getattr(record, "failure_class", "-"),
            "skill_id": getattr(record, "skill_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


API_LOG_FORMAT = (
    "%(asctime)s %(levelname)s [api] "
    "request_id=%(request_id)s run_id=%(run_id)s "
    "status=%(status)s failure_class=%(failure_class)s "
    "skill_id=%(skill_id)s %(message)s"
)

WORKER_LOG_FORMAT = (
    "%(asctime)s %(levelname)s [worker] "
    "request_id=%(request_id)s run_id=%(run_id)s "
    "status=%(status)s failure_class=%(failure_class)s "
    "skill_id=%(skill_id)s %(message)s"
)


def _resolve_level(level: str) -> int:
    return getattr(logging, (level or "INFO").upper(), logging.INFO)


def configure_logging(*, role: str = "api", log_format: str = "text", log_level: str = "INFO") -> None:
    """Install correlation filter + text/json formatter on the root logger."""
    root = logging.getLogger()
    root.setLevel(_resolve_level(log_level))
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        root.addHandler(handler)

    use_json = (log_format or "text").strip().lower() == "json"
    text_fmt = WORKER_LOG_FORMAT if role == "worker" else API_LOG_FORMAT

    for handler in root.handlers:
        handler.addFilter(ContextFieldsFilter())
        if use_json:
            handler.setFormatter(JsonLogFormatter())
        else:
            handler.setFormatter(logging.Formatter(text_fmt))


def configure_api_logging(*, log_format: str = "text", log_level: str = "INFO") -> None:
    configure_logging(role="api", log_format=log_format, log_level=log_level)


def configure_worker_logging(*, log_format: str = "text", log_level: str = "INFO") -> None:
    """Install Trace-aligned format for the analysis worker process."""
    configure_logging(role="worker", log_format=log_format, log_level=log_level)
