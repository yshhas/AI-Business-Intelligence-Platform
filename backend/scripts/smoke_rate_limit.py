"""P0 smoke: auth rate limit returns 429 (Redis + DB required)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

# Must set before Settings cache / app import effects on checks
os.environ["RATE_LIMIT_ENABLED"] = "true"
os.environ["RATE_LIMIT_AUTH_PER_MINUTE"] = "3"

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.queue import get_redis  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.rate_limit_enabled is True
    assert settings.rate_limit_auth_per_minute == 3

    # Isolate keys for this run
    email = f"rl_{uuid4().hex[:8]}@example.com"
    client = TestClient(app)

    # Ensure redis reachable
    assert get_redis().ping() is True

    statuses: list[int] = []
    for _ in range(6):
        res = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "wrong-password"},
        )
        statuses.append(res.status_code)

    assert any(s == 429 for s in statuses), statuses
    assert statuses.count(401) >= 1, statuses  # some attempts before limit
    print("RATE_LIMIT_OK", statuses)


if __name__ == "__main__":
    main()
