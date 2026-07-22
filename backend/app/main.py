from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_auth import router as auth_router
from app.api.routes_datasets import router as datasets_router
from app.api.routes_health import router as health_router
from app.api.routes_mcp import router as mcp_router
from app.api.routes_tasks import router as tasks_router
from app.api.routes_workspaces import router as workspaces_router
from app.core.config import assert_boot_runtime, assert_boot_security, get_settings
from app.core.observability import configure_api_logging
from app.middleware.request_id import RequestIdMiddleware
from app.services import skill_lifecycle as skills


def create_app() -> FastAPI:
    settings = get_settings()
    assert_boot_security(settings)
    assert_boot_runtime(settings)
    configure_api_logging(log_format=settings.log_format, log_level=settings.log_level)
    try:
        skills.sync_from_settings(settings)
    except Exception:  # noqa: BLE001 — agent path optional at import time
        pass
    app = FastAPI(title=settings.app_name, version="1.0.0")

    # Last add_middleware is outermost: CORS → RequestId → routes.
    app.add_middleware(RequestIdMiddleware)
    origins = settings.cors_origin_list() or [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(workspaces_router)
    app.include_router(datasets_router)
    app.include_router(tasks_router)
    app.include_router(mcp_router)
    return app


app = create_app()
