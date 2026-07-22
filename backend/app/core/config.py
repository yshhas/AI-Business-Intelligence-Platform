from functools import lru_cache
from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default / placeholder secrets that must never ship in production/staging.
WEAK_JWT_SECRETS = frozenset(
    {
        "change-me-in-phase-1-use-a-long-random-string",
        "ci-only-not-for-production",
        "secret",
        "changeme",
        "jwt-secret",
    }
)


class Settings(BaseSettings):
    """Runtime settings loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        # Prefer repo-root `.env`, fall back to `backend/.env`.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Business Intelligence Platform"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # T-08 — logging: text (local) | json (collectable)
    log_format: str = "text"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://aibi:aibi_dev_password@localhost:5432/aibi"
    redis_url: str = "redis://localhost:6379/0"

    # Auth — short-lived access + longer refresh (P0 Trust)
    jwt_secret: str = "change-me-in-phase-1-use-a-long-random-string"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 60 * 24 * 7
    # Comma-separated browser origins for CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # P0 Rate limits (Redis). Disabled only for tightly scoped local debugging.
    rate_limit_enabled: bool = True
    rate_limit_auth_per_minute: int = 30
    rate_limit_task_create_per_minute: int = 60

    # P1 — Worker HTTP health probe (0 disables)
    worker_health_host: str = "0.0.0.0"
    worker_health_port: int = 8001
    # P1 — expose Prometheus /metrics on API
    metrics_enabled: bool = True

    # Phase 2+ — relative paths resolve from repo root (see storage_paths.py)
    upload_dir: str = "./data/uploads"
    duckdb_dir: str = "./data/duckdb"
    max_upload_bytes: int = 20 * 1024 * 1024  # 20 MiB MVP cap

    # Phase 3 — async task skeleton
    analysis_runtime: str = "mock"  # mock | agent
    analysis_queue_key: str = "aibi:analysis_tasks"
    redis_brpop_timeout_seconds: int = 5

    # Phase 4 — agent / SQL
    sql_default_limit: int = 200
    sql_max_retries: int = 2
    llm_api_key: str = ""
    # Wave 2: openai_compatible | anthropic | gemini (defaults base_url/model when empty)
    llm_provider: str = "openai_compatible"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    # When LLM key is empty, allow deterministic heuristic SQL (dev/golden-path only)
    allow_heuristic_sql: bool = True
    # T-04 — LLM HTTP retry (not SQL Gate / graph retries). Retries after first attempt.
    llm_max_retries: int = 2
    llm_retry_backoff_seconds: float = 0.5
    llm_retry_backoff_max_seconds: float = 8.0

    # Phase M2 — Run lifecycle
    run_timeout_seconds: int = 120

    # Phase E3 — Runtime Essentials (Worker / queue governance)
    # Max concurrent status=running Runs (global). Enqueue + claim both respect this.
    run_max_in_flight: int = 4
    # Max Redis List depth before enqueue reject (LLEN).
    analysis_queue_max_depth: int = 50
    # Stale running reclaim TTL seconds; <=0 means run_timeout_seconds + 60.
    stale_running_seconds: int = 0
    # Heartbeat refresh while running (0 = disable updates; still reclaim via started_at).
    run_heartbeat_interval_seconds: int = 15

    # Phase M3 — Postgres read-only data plane (separate from database_url)
    # Example: postgresql://aibi_ro:aibi_ro_password@localhost:5434/aibi_data
    postgres_ro_dsn: str = ""
    # Wave 3 — optional MySQL RO plane (mysql://user:pass@host:3306/dbname)
    mysql_ro_dsn: str = ""

    # T-09 / Wave 3 — Skill Lifecycle lite (no marketplace)
    skill_data_bi_enabled: bool = True
    skill_data_bi_version: str = "1.0.0"
    skill_data_profile_enabled: bool = True
    skill_data_profile_version: str = "1.0.0"

    # Wave 3 — OIDC MVP (disabled unless oidc_enabled + issuer/client/redirect set)
    oidc_enabled: bool = False
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_scopes: str = "openid email profile"

    # Wave 3 — Workspace memory (synonym persist from successful Runs)
    workspace_memory_enabled: bool = True

    # T-10 — SSE task progress (DB poll; not LLM token stream)
    task_sse_poll_seconds: float = 0.5
    task_sse_heartbeat_seconds: float = 5.0
    task_sse_max_seconds: float = 600.0

    # P0-2 Soft Cost Budget — workspace UTC-day LLM tokens (0 = disabled)
    # Soft: rejects new enqueue only; does not kill in-flight Runs. Not FinOps.
    llm_token_budget_per_workspace_day: int = 0

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _strip_cors(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def _harden_env(self) -> Self:
        env = (self.app_env or "").strip().lower()
        # Production/staging: never allow heuristic SQL escape hatch.
        if env in {"production", "staging"}:
            object.__setattr__(self, "allow_heuristic_sql", False)
        return self

    def cors_origin_list(self) -> list[str]:
        parts = [p.strip() for p in (self.cors_origins or "").split(",")]
        return [p for p in parts if p]

    def is_hardened_env(self) -> bool:
        return (self.app_env or "").strip().lower() in {"production", "staging"}


def assert_boot_security(settings: Settings | None = None) -> None:
    """Fail fast on weak JWT secrets in hardened environments."""
    cfg = settings or get_settings()
    secret = (cfg.jwt_secret or "").strip()
    if not cfg.is_hardened_env():
        return
    if not secret or secret in WEAK_JWT_SECRETS or len(secret) < 32:
        raise RuntimeError(
            "Refusing to start: JWT_SECRET is missing, weak, or too short "
            f"for APP_ENV={cfg.app_env!r}. Use a random secret >= 32 characters."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
