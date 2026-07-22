"""P0 smoke: production profile rejects weak JWT and forces heuristic off."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import (  # noqa: E402
    WEAK_JWT_SECRETS,
    Settings,
    assert_boot_security,
    get_settings,
)


def main() -> None:
    get_settings.cache_clear()

    # Development: weak secret allowed at boot
    dev = Settings(app_env="development", jwt_secret="change-me-in-phase-1-use-a-long-random-string")
    assert_boot_security(dev)

    # Production: weak secret rejected
    prod_weak = Settings(app_env="production", jwt_secret="change-me-in-phase-1-use-a-long-random-string")
    assert prod_weak.allow_heuristic_sql is False
    try:
        assert_boot_security(prod_weak)
        raise SystemExit("expected RuntimeError for weak JWT in production")
    except RuntimeError as exc:
        assert "JWT_SECRET" in str(exc)

    # Production: short secret rejected
    prod_short = Settings(app_env="production", jwt_secret="short-but-not-default")
    try:
        assert_boot_security(prod_short)
        raise SystemExit("expected RuntimeError for short JWT in production")
    except RuntimeError:
        pass

    # Production: strong secret ok; heuristic forced off even if env tried true
    strong = "x" * 32
    assert strong not in WEAK_JWT_SECRETS
    prod_ok = Settings(
        app_env="production",
        jwt_secret=strong,
        allow_heuristic_sql=True,
    )
    assert prod_ok.allow_heuristic_sql is False
    assert_boot_security(prod_ok)

    # CORS parsing
    s = Settings(cors_origins="http://a.example, http://b.example")
    assert s.cors_origin_list() == ["http://a.example", "http://b.example"]

    print("CONFIG_HARDENING_OK")


if __name__ == "__main__":
    # Avoid leaking production env into process defaults for other smokes
    os.environ.pop("APP_ENV", None)
    main()
