"""T-12 smoke: Docker Compose app stack wiring (static; no daemon required).

Validates Dockerfile + compose define api/worker alongside existing infra.
Live bring-up is operator-side (see docs/OPS_RUNBOOK.md).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKER = ROOT / "docker"


def main() -> None:
    dockerfile = DOCKER / "Dockerfile"
    entry = DOCKER / "entrypoint.py"
    compose = DOCKER / "docker-compose.yml"
    dockerignore = ROOT / ".dockerignore"

    assert dockerfile.is_file(), f"missing {dockerfile}"
    assert entry.is_file(), f"missing {entry}"
    assert compose.is_file(), f"missing {compose}"
    assert dockerignore.is_file(), f"missing {dockerignore}"
    print("DOCKER_FILES_OK")

    df = dockerfile.read_text(encoding="utf-8")
    assert "COPY agent" in df
    assert "COPY backend" in df
    assert "entrypoint.py" in df
    print("DOCKERFILE_LAYOUT_OK")

    ep = entry.read_text(encoding="utf-8")
    assert "alembic" in ep
    assert "uvicorn" in ep
    assert "analysis_worker" in ep
    assert 'APP_ROLE' in ep or "app_role" in ep.lower() or 'get("APP_ROLE"' in ep
    print("ENTRYPOINT_ROLES_OK")

    text = compose.read_text(encoding="utf-8")
    for svc in ("postgres:", "redis:", "postgres_ro:", "api:", "worker:"):
        assert re.search(rf"(?m)^\s*{re.escape(svc)}", text), f"compose missing service {svc}"
    assert "APP_ROLE: api" in text
    assert "APP_ROLE: worker" in text
    assert "@postgres:5432" in text
    assert "redis://redis:6379" in text
    assert "@postgres_ro:5432" in text
    assert "../data:/app/data" in text
    assert "health/ready" in text
    print("COMPOSE_SERVICES_OK")
    print("OK: smoke_docker_compose")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
