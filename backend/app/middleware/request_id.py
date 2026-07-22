"""HTTP middleware: ensure every request has a correlatable request_id (T-08)."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.observability import (
    REQUEST_ID_HEADER,
    new_request_id,
    reset_request_id,
    set_request_id,
)

logger = logging.getLogger("app.request")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER) or request.headers.get(
            "x-request-id"
        )
        rid = (incoming or "").strip() or new_request_id()
        token = set_request_id(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = rid
            duration_ms = int((time.perf_counter() - started) * 1000)
            path = request.url.path
            if path not in {"/health", "/health/live", "/health/ready"}:
                logger.info(
                    "request method=%s path=%s status_code=%s duration_ms=%s",
                    request.method,
                    path,
                    response.status_code,
                    duration_ms,
                    extra={
                        "request_id": rid,
                        "run_id": "-",
                        "status": str(response.status_code),
                        "failure_class": "-",
                        "skill_id": "-",
                    },
                )
            return response
        except Exception:
            logger.exception(
                "request failed method=%s path=%s",
                request.method,
                request.url.path,
                extra={
                    "request_id": rid,
                    "run_id": "-",
                    "status": "error",
                    "failure_class": "-",
                    "skill_id": "-",
                },
            )
            raise
        finally:
            reset_request_id(token)
