"""Wave 2 smoke: OpenAPI contract paths + AuthResponse.refresh_token."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def main() -> None:
    client = TestClient(app)
    res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    spec = res.json()
    paths = spec.get("paths") or {}

    required_paths = [
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/oidc/login",
        "/health/ready",
        "/metrics",
    ]
    for path in required_paths:
        assert path in paths, f"missing OpenAPI path {path!r}; have {sorted(paths)[:20]}…"

    schemas = spec.get("components", {}).get("schemas") or {}
    auth = schemas.get("AuthResponse")
    if auth is not None:
        props = auth.get("properties") or {}
        assert "refresh_token" in props, f"AuthResponse missing refresh_token; keys={sorted(props)}"

    print("OPENAPI_CONTRACT_OK")


if __name__ == "__main__":
    main()
