"""P1 smoke: Prometheus /metrics + Worker health HTTP."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.metrics import observe_enqueue, observe_task_terminal, render_metrics  # noqa: E402
from app.main import app  # noqa: E402
from app.workers.health_server import start_worker_health_server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from urllib.request import urlopen  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.metrics_enabled is True

    observe_enqueue("ok")
    observe_task_terminal(status="succeeded", failure_class=None)
    body, ctype = render_metrics()
    text = body.decode("utf-8")
    assert "aibi_enqueue_total" in text
    assert "aibi_tasks_terminal_total" in text
    assert "aibi_queue_depth" in text
    assert "text/plain" in ctype or "openmetrics" in ctype or "prometheus" in ctype.lower() or ctype.startswith(
        "text/"
    )

    client = TestClient(app)
    res = client.get("/metrics")
    assert res.status_code == 200, res.text
    assert b"aibi_enqueue_total" in res.content

    # Worker health on ephemeral port
    server = start_worker_health_server(host="127.0.0.1", port=18001)
    assert server is not None
    try:
        with urlopen("http://127.0.0.1:18001/health/live", timeout=2) as resp:
            live = resp.read().decode("utf-8")
        assert '"probe": "live"' in live or '"probe":"live"' in live
        assert '"role": "worker"' in live or '"role":"worker"' in live
    finally:
        server.shutdown()

    print("METRICS_WORKER_HEALTH_OK")


if __name__ == "__main__":
    main()
