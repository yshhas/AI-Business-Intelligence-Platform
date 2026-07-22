"""Health probes — liveness vs readiness (DH.2 + P1 Worker health).

Liveness: process up (cheap).
Readiness: DB + Redis available (safe for Demo traffic / enqueue).
Worker: separate HTTP on WORKER_HEALTH_PORT (default 8001) — see OPS_RUNBOOK.md.
Prometheus: GET /metrics on the API when METRICS_ENABLED=true.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import SessionLocal, get_dialect_name
from app.core.repo_path import ensure_repo_root_on_path

router = APIRouter(tags=["health"])


def _platform_registry() -> dict:
    try:
        from app.core.config import get_settings
        from app.services import skill_lifecycle as skills

        settings = get_settings()
        catalog = skills.catalog(settings)
        return {
            "skills": catalog,
            "tools": _tools_only(),
            "policies": _policies_only(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"agent_registry": f"unavailable: {exc}"}


def _tools_only() -> list:
    try:
        ensure_repo_root_on_path()
        from agent.kernel.runtime import platform_info

        return [t["tool_id"] for t in platform_info().get("tools", [])]
    except Exception:  # noqa: BLE001
        return []


def _policies_only() -> list:
    try:
        ensure_repo_root_on_path()
        from agent.kernel.runtime import platform_info

        return [p["policy_id"] for p in platform_info().get("policies", [])]
    except Exception:  # noqa: BLE001
        return []


def _redis_status() -> str:
    try:
        from app.services import queue as task_queue

        return "ok" if task_queue.ping() else "error"
    except Exception:  # noqa: BLE001
        return "error"


def _db_status() -> str:
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            return "ok"
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        return "error"


@router.get("/health/live")
def health_live() -> dict:
    """Liveness — process is up (no dependency checks)."""
    settings = get_settings()
    return {
        "status": "ok",
        "probe": "live",
        "app": settings.app_name,
        "env": settings.app_env,
        "platform": "enterprise-data-agent",
    }


@router.get("/health/ready")
def health_ready() -> Response:
    """Readiness — DB + Redis must be ok for enqueue / Demo traffic."""
    settings = get_settings()
    db = _db_status()
    redis = _redis_status()
    ready = db == "ok" and redis == "ok"
    payload = {
        "status": "ok" if ready else "not_ready",
        "probe": "ready",
        "app": settings.app_name,
        "env": settings.app_env,
        "platform": "enterprise-data-agent",
        "db": db,
        "db_dialect": get_dialect_name(),
        "redis": redis,
        "analysis_runtime": settings.analysis_runtime,
        "capacity": {
            "run_max_in_flight": settings.run_max_in_flight,
            "analysis_queue_max_depth": settings.analysis_queue_max_depth,
        },
        **_platform_registry(),
    }
    code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=payload, status_code=code)


@router.get("/health")
def health() -> Response:
    """Backward-compatible aggregate: same checks as ready + live identity."""
    return health_ready()


@router.get("/metrics")
def metrics() -> Response:
    """Prometheus text exposition (P1)."""
    settings = get_settings()
    if not settings.metrics_enabled:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "metrics disabled"},
        )
    from app.core.metrics import render_metrics

    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)