"""Prometheus metrics (P1) — thin counters/gauges for API + Worker.

Not a full observability platform. Scrape GET /metrics on the API.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

ENQUEUE_TOTAL = Counter(
    "aibi_enqueue_total",
    "Analyze enqueue outcomes",
    ["result"],
)

TASKS_TERMINAL_TOTAL = Counter(
    "aibi_tasks_terminal_total",
    "Analysis tasks reaching a terminal status",
    ["status", "failure_class"],
)

QUEUE_DEPTH = Gauge(
    "aibi_queue_depth",
    "Redis analysis queue list length (LLEN)",
)

RUNS_IN_FLIGHT = Gauge(
    "aibi_runs_in_flight",
    "Count of analysis_tasks with status=running",
)

RATE_LIMIT_TOTAL = Counter(
    "aibi_rate_limit_total",
    "HTTP rate-limit rejections",
    ["scope"],
)


def observe_enqueue(result: str) -> None:
    ENQUEUE_TOTAL.labels(result=result).inc()


def observe_task_terminal(*, status: str, failure_class: str | None = None) -> None:
    TASKS_TERMINAL_TOTAL.labels(
        status=status,
        failure_class=(failure_class or "none"),
    ).inc()


def observe_rate_limit(scope: str) -> None:
    RATE_LIMIT_TOTAL.labels(scope=scope).inc()


def refresh_runtime_gauges() -> None:
    """Best-effort snapshot for scrapes (API process)."""
    try:
        from app.core.config import get_settings
        from app.core.db import SessionLocal
        from app.services import queue as task_queue
        from app.services import runtime_essentials as rt

        QUEUE_DEPTH.set(float(task_queue.queue_length()))
        db = SessionLocal()
        try:
            RUNS_IN_FLIGHT.set(float(rt.count_running(db)))
        finally:
            db.close()
        _ = get_settings()
    except Exception:  # noqa: BLE001
        pass


def render_metrics() -> tuple[bytes, str]:
    refresh_runtime_gauges()
    return generate_latest(), CONTENT_TYPE_LATEST


def metrics_snapshot() -> dict[str, Any]:
    """Non-Prometheus JSON helper for smokes / debugging."""
    refresh_runtime_gauges()
    return {
        "queue_depth": float(QUEUE_DEPTH.collect()[0].samples[0].value),
        "runs_in_flight": float(RUNS_IN_FLIGHT.collect()[0].samples[0].value),
    }
