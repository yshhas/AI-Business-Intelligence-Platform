"""P0+P1.2 smoke: access + refresh JWT pair with jti revoke / rotation."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
# Force P0 defaults regardless of developer .env long-TTL leftovers.
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["REFRESH_TOKEN_EXPIRE_MINUTES"] = "10080"

from app.core.config import get_settings  # noqa: E402
from app.core.security import (  # noqa: E402
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_token,
)
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.access_token_expire_minutes == 30, settings.access_token_expire_minutes
    assert settings.refresh_token_expire_minutes == 10080

    client = TestClient(app)
    email = f"auth_refresh_{uuid4().hex[:8]}@example.com"
    password = "password123"

    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": "Refresh"},
    )
    assert reg.status_code == 201, reg.text
    body = reg.json()
    assert body.get("access_token")
    assert body.get("refresh_token")
    access = body["access_token"]
    refresh = body["refresh_token"]

    access_payload = decode_access_token(access)
    assert access_payload["type"] == "access"
    refresh_payload = decode_token(refresh, expected_type="refresh")
    assert refresh_payload["type"] == "refresh"
    assert refresh_payload.get("jti")

    # Refresh token must not work as Bearer access
    bad = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert bad.status_code == 401, bad.text

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200, me.text
    assert me.json()["email"] == email

    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert rotated.status_code == 200, rotated.text
    new_body = rotated.json()
    assert new_body["access_token"] != access
    assert new_body.get("refresh_token")
    new_refresh = new_body["refresh_token"]

    # P1.2: old refresh jti must fail after rotation (reuse → 401, no family kill)
    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert reuse.status_code == 401, reuse.text
    print("REFRESH_ROTATION_REUSE_401_OK")

    me2 = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_body['access_token']}"},
    )
    assert me2.status_code == 200, me2.text

    # Access token rejected by refresh endpoint
    wrong = client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert wrong.status_code == 401, wrong.text

    # Multi-device: second login creates another live session
    login2 = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login2.status_code == 200, login2.text
    device_b = login2.json()["refresh_token"]
    assert device_b != new_refresh

    # Logout current device (device A = new_refresh) — device B still works
    lo = client.post("/api/v1/auth/logout", json={"refresh_token": new_refresh})
    assert lo.status_code == 204, lo.text
    dead = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert dead.status_code == 401, dead.text
    print("LOGOUT_CURRENT_SESSION_OK")

    still = client.post("/api/v1/auth/refresh", json={"refresh_token": device_b})
    assert still.status_code == 200, still.text
    print("MULTI_DEVICE_SESSION_OK")

    # Idempotent logout on already-revoked / garbage
    lo2 = client.post("/api/v1/auth/logout", json={"refresh_token": new_refresh})
    assert lo2.status_code == 204, lo2.text

    # Unit: create_* helpers agree on types (stateless mint; not a live session)
    uid = me.json()["id"]
    a2 = create_access_token(user_id=UUID(uid), email=email)
    r2 = create_refresh_token(user_id=UUID(uid), email=email)
    assert decode_access_token(a2)["type"] == "access"
    assert decode_token(r2, expected_type="refresh")["type"] == "refresh"

    print("AUTH_REFRESH_OK")


if __name__ == "__main__":
    main()
