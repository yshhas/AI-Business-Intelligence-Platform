"""T-08 smoke: request_id middleware + JSON structured logs (no infra required)."""

from __future__ import annotations

import json
import logging
import sys
from io import StringIO
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.observability import (  # noqa: E402
    ContextFieldsFilter,
    JsonLogFormatter,
    configure_logging,
    get_request_id,
    log_run,
    reset_request_id,
    set_request_id,
)
from app.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def main() -> None:
    get_settings.cache_clear()

    # --- middleware: echo / generate X-Request-ID ---
    app = create_app()
    client = TestClient(app)

    r1 = client.get("/health/live")
    assert r1.status_code == 200
    rid1 = r1.headers.get("X-Request-ID")
    assert rid1 and len(rid1) >= 8

    custom = f"req-{uuid4().hex[:12]}"
    r2 = client.get("/health/live", headers={"X-Request-ID": custom})
    assert r2.status_code == 200
    assert r2.headers.get("X-Request-ID") == custom
    print("REQUEST_ID_MIDDLEWARE_OK")

    # --- JSON formatter + log_run fields ---
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    handler.addFilter(ContextFieldsFilter())

    test_logger = logging.getLogger("smoke.t08")
    test_logger.handlers.clear()
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)
    test_logger.propagate = False

    token = set_request_id("req-smoke-1")
    try:
        log_run(
            test_logger,
            logging.INFO,
            "enqueued",
            run_id="11111111-1111-1111-1111-111111111111",
            status="pending",
            skill_id="data.bi",
        )
    finally:
        reset_request_id(token)

    line = stream.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["request_id"] == "req-smoke-1"
    assert payload["run_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["skill_id"] == "data.bi"
    assert payload["status"] == "pending"
    assert "enqueued" in payload["msg"]
    print("JSON_LOG_FORMAT_OK")

    configure_logging(role="api", log_format="json", log_level="INFO")
    assert get_request_id() == "-"
    print("OBSERVABILITY_T08_OK")


if __name__ == "__main__":
    main()
