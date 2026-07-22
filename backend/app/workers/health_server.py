"""Tiny HTTP health server for the Analysis Worker (P1).

Runs in a daemon thread so Compose/K8s can probe the Worker without sharing
the API process. Not a second product surface.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

logger = logging.getLogger("app.worker.health")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        logger.debug("worker_health %s", format % args)

    def _send(self, code: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        from app.core.config import get_settings

        settings = get_settings()
        path = self.path.split("?", 1)[0]

        if path in {"/health/live", "/health"}:
            self._send(
                200,
                {
                    "status": "ok",
                    "probe": "live",
                    "role": "worker",
                    "app": settings.app_name,
                    "env": settings.app_env,
                    "analysis_runtime": settings.analysis_runtime,
                },
            )
            return

        if path == "/health/ready":
            redis_ok = False
            try:
                from app.services import queue as task_queue

                redis_ok = bool(task_queue.ping())
            except Exception:  # noqa: BLE001
                redis_ok = False
            code = 200 if redis_ok else 503
            self._send(
                code,
                {
                    "status": "ok" if redis_ok else "not_ready",
                    "probe": "ready",
                    "role": "worker",
                    "app": settings.app_name,
                    "env": settings.app_env,
                    "analysis_runtime": settings.analysis_runtime,
                    "redis": "ok" if redis_ok else "error",
                },
            )
            return

        self._send(404, {"status": "not_found", "probe": "none"})


def start_worker_health_server(*, host: str, port: int) -> ThreadingHTTPServer | None:
    if port <= 0:
        logger.info("worker health HTTP disabled (port<=0)")
        return None
    server = ThreadingHTTPServer((host, port), _Handler)
    thread = threading.Thread(
        target=server.serve_forever,
        name="worker-health",
        daemon=True,
    )
    thread.start()
    logger.info("worker health listening on http://%s:%s/health/live", host, port)
    return server
