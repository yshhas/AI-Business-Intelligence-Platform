"""T-12 container entry — APP_ROLE=api|worker|migrate (no shell CRLF issues on Windows)."""

from __future__ import annotations

import os
import subprocess
import sys


def _alembic_upgrade() -> None:
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"])


def main() -> None:
    role = (os.environ.get("APP_ROLE") or "api").strip().lower()
    # Ensure cwd is backend/ for alembic.ini + `app` package
    os.chdir("/app/backend")

    if role == "migrate":
        _alembic_upgrade()
        return

    if role == "api":
        # Idempotent; worker waits for API healthy so schema is ready first.
        _alembic_upgrade()
        port = os.environ.get("API_PORT", "8000")
        os.execvp(
            sys.executable,
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(port),
            ],
        )

    if role == "worker":
        os.execvp(
            sys.executable,
            [sys.executable, "-m", "app.workers.analysis_worker"],
        )

    print(f"Unknown APP_ROLE={role!r}; expected api|worker|migrate", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
