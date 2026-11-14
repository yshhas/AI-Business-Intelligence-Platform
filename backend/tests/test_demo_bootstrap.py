"""Regression test for demo_bootstrap.py exit codes (Phase 1 R1).

Runs the script as a subprocess against a local stub API so the process exit
code can be asserted without Postgres / Redis / a real LLM.

Locks in the fix: a failed assertion must never be reported as success, even
when the Run itself reached status=succeeded (e.g. a heuristic fallback caught
by --expect-llm).
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_bootstrap.py"

WS = "11111111-1111-1111-1111-111111111111"
DS = "22222222-2222-2222-2222-222222222222"
TASK = "33333333-3333-3333-3333-333333333333"

_PASS_RESULT = {
    "sql": "SELECT region, SUM(amount) FROM demo_orders GROUP BY region",
    "table_preview": {"columns": ["region", "total"], "rows": [{"region": "North", "total": 1}], "row_count": 1},
    "charts": [{"id": "c1", "type": "bar", "title": "region", "spec": {"x": {}, "y": {}, "data": {}}}],
    "report": {"title": "报告", "markdown": "# 报告"},
}
_PASS_LLM = {"model": "stub", "latency_ms": 12, "attempts": 1, "status": "ok", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


def _execution() -> dict:
    return {
        "execution": {
            "schema_version": 1,
            "tool_calls": [{"call_id": "tc_1", "tool_id": "sql.generate"}],
            "policy_decisions": [{"decision_id": "pd_1", "policy_id": "sql.select_gate", "ok": True}],
            "artifacts": [{"artifact_id": "a1", "type": "sql"}],
            "summary": {"tool_count": 1},
        }
    }


class _Stub(BaseHTTPRequestHandler):
    """Minimal stand-in for the platform API. `mode` selects pass vs heuristic."""

    mode = "pass"

    def log_message(self, *args):  # silence
        return

    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _drain(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)

    # -- GET --------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/health/ready":
            return self._send(200, {"status": "ok"})
        if path == f"/api/v1/workspaces/{WS}/datasets":
            return self._send(200, {"items": []})
        if path == f"/api/v1/workspaces/{WS}/tasks/{TASK}":
            heuristic = self.mode == "heuristic"
            return self._send(
                200,
                {
                    "id": TASK,
                    "status": "succeeded",  # Run itself always succeeds
                    "result_json": {
                        "sql": "" if heuristic else _PASS_RESULT["sql"],
                        "table_preview": {} if heuristic else _PASS_RESULT["table_preview"],
                        "charts": [] if heuristic else _PASS_RESULT["charts"],
                        "report": {} if heuristic else _PASS_RESULT["report"],
                    },
                    "llm_total_tokens": 0 if heuristic else 15,
                },
            )
        if path == f"/api/v1/workspaces/{WS}/tasks/{TASK}/steps":
            llm = {"status": "skipped", "mode": "heuristic"} if self.mode == "heuristic" else _PASS_LLM
            return self._send(200, {"items": [{"node_name": "generate_sql", "output_json": {"llm": llm}}]})
        if path == f"/api/v1/workspaces/{WS}/tasks/{TASK}/execution":
            if self.mode == "heuristic":
                return self._send(200, {"execution": {"tool_calls": [], "policy_decisions": [], "artifacts": []}})
            return self._send(200, _execution())
        if path == f"/api/v1/workspaces/{WS}/tasks/{TASK}/artifacts":
            items = [] if self.mode == "heuristic" else [{"id": "a1", "type": "sql"}]
            return self._send(200, {"items": items})
        return self._send(404, {"detail": "not found"})

    # -- POST -------------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        self._drain()
        path = self.path.split("?", 1)[0]
        if path == "/api/v1/auth/register":
            return self._send(
                201,
                {
                    "access_token": "stub-token",
                    "refresh_token": "stub-refresh",
                    "user": {"id": "u1", "email": "demo@example.com", "display_name": "Demo", "created_at": "2026-01-01T00:00:00Z"},
                    "workspace": {"id": WS, "name": "ws", "role": "owner", "created_at": "2026-01-01T00:00:00Z"},
                },
            )
        if path.endswith("/datasets/postgres-ro"):
            return self._send(201, {"id": DS, "name": "demo", "source_type": "postgres_ro", "row_count": 8})
        if path == f"/api/v1/workspaces/{WS}/tasks":
            return self._send(201, {"id": TASK, "status": "pending"})
        return self._send(404, {"detail": "not found"})


def _run_script(mode: str, *extra: str) -> subprocess.CompletedProcess:
    _Stub.mode = mode
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--base-url", base, "--ask", "q", *extra],
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        server.shutdown()
        server.server_close()


def test_all_assertions_pass_returns_zero():
    proc = _run_script("pass", "--expect-llm")
    assert "ALL PASSED" in proc.stdout, proc.stdout
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_failed_assertion_with_succeeded_run_returns_nonzero():
    """R1 regression: succeeded Run + failed assertions must NOT return 0."""
    proc = _run_script("heuristic")
    assert "FAILED" in proc.stdout, proc.stdout
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert proc.returncode == 2, proc.stdout + proc.stderr


def test_expect_llm_rejects_heuristic_fallback():
    """--expect-llm must fail the process when the run fell back to heuristic."""
    proc = _run_script("heuristic", "--expect-llm")
    assert "未走 heuristic 回退" in proc.stdout, proc.stdout
    assert proc.stdout.count("FAIL") >= 1
    assert proc.returncode != 0, proc.stdout + proc.stderr
