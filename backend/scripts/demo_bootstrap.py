"""Phase 1 demo bootstrap — drives the platform through its real HTTP API.

Registers a user, binds the compose-seeded postgres_ro demo tables as a Dataset,
optionally submits a question and verifies a full Agent run.

Design constraints (Phase 1):
  * Pure HTTP. No direct DB writes, no service-layer imports.
  * No bypass of auth / Policy / SQL Gate / HITL.
  * No mock or heuristic shortcut is treated as a successful LLM demo.
  * Idempotent: re-running reuses the existing user / workspace / dataset.

Usage (repo root, with the compose stack up):

    python backend/scripts/demo_bootstrap.py
    python backend/scripts/demo_bootstrap.py --ask "各区域订单总金额是多少？按金额降序"
    python backend/scripts/demo_bootstrap.py --ask "..." --expect-llm

Exit codes:
    0  bootstrap ok (and the run passed every assertion when --ask was given)
    1  bootstrap failed
    2  bootstrap ok, but a requested --ask run failed verification / was heuristic
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

import httpx

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "timed_out"}
PARKED_STATUSES = {"awaiting_approval"}

DEFAULT_TABLES = ["public.demo_orders", "public.demo_customers"]
DEFAULT_QUESTION = "各区域订单总金额是多少？按金额降序"


class DemoError(RuntimeError):
    """Bootstrap step failed."""


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #


def _fail(resp: httpx.Response, what: str) -> None:
    detail = resp.text[:400] if resp.text else ""
    raise DemoError(f"{what} failed: HTTP {resp.status_code} {detail}")


def register_or_login(client: httpx.Client, *, email: str, password: str, display: str) -> dict[str, Any]:
    """Register a new user, or fall back to login when the email already exists."""
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": display},
    )
    if resp.status_code == 201:
        print(f"[ok]  registered {email}")
        return resp.json()
    if resp.status_code == 409:
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        if resp.status_code != 200:
            _fail(resp, f"login for existing user {email}")
        print(f"[ok]  logged in as existing user {email}")
        return resp.json()
    _fail(resp, f"register {email}")
    raise AssertionError("unreachable")


def resolve_workspace(client: httpx.Client, auth: dict[str, Any]) -> str:
    """Prefer the workspace returned by auth; fall back to listing memberships."""
    ws = auth.get("workspace")
    if isinstance(ws, dict) and ws.get("id"):
        print(f"[ok]  workspace {ws['id']} ({ws.get('role')})")
        return str(ws["id"])

    resp = client.get("/api/v1/workspaces")
    if resp.status_code != 200:
        _fail(resp, "list workspaces")
    items = resp.json().get("items") or []
    if not items:
        raise DemoError("no workspace found for this user")
    print(f"[ok]  workspace {items[0]['id']} ({items[0].get('role')})")
    return str(items[0]["id"])


def ensure_postgres_ro_dataset(client: httpx.Client, *, workspace_id: str, name: str) -> dict[str, Any]:
    """Bind the seeded postgres_ro demo tables as a Dataset (reuse if present)."""
    resp = client.get(f"/api/v1/workspaces/{workspace_id}/datasets")
    if resp.status_code != 200:
        _fail(resp, "list datasets")
    for item in resp.json().get("items") or []:
        if item.get("name") == name:
            print(f"[ok]  reusing dataset {item['id']} ({item.get('source_type')})")
            return item

    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets/postgres-ro",
        json={"name": name, "tables": DEFAULT_TABLES},
    )
    if resp.status_code != 201:
        _fail(resp, f"bind postgres-ro dataset (tables={DEFAULT_TABLES})")
    ds = resp.json()
    print(f"[ok]  bound dataset {ds['id']} tables={DEFAULT_TABLES} rows={ds.get('row_count')}")
    return ds


def create_task(client: httpx.Client, *, workspace_id: str, dataset_id: str, question: str) -> dict[str, Any]:
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/tasks",
        json={"dataset_id": dataset_id, "question": question},
    )
    if resp.status_code != 201:
        _fail(resp, "create task")
    task = resp.json()
    print(f"[ok]  task {task['id']} status={task['status']}")
    return task


def poll_task(
    client: httpx.Client, *, workspace_id: str, task_id: str, timeout: float, interval: float
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last = ""
    while True:
        resp = client.get(f"/api/v1/workspaces/{workspace_id}/tasks/{task_id}")
        if resp.status_code != 200:
            _fail(resp, "poll task")
        task = resp.json()
        status = str(task.get("status"))
        if status != last:
            print(f"[..]  status={status}")
            last = status
        if status in TERMINAL_STATUSES:
            return task
        if status in PARKED_STATUSES:
            raise DemoError(
                f"task parked in {status}: HITL approval is required. "
                "Approve it via POST .../tasks/{id}/approve, or run with HITL disabled."
            )
        if time.monotonic() > deadline:
            raise DemoError(f"task still {status} after {timeout:.0f}s (timeout)")
        time.sleep(interval)


def fetch_run_details(
    client: httpx.Client, *, workspace_id: str, task_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    base = f"/api/v1/workspaces/{workspace_id}/tasks/{task_id}"
    steps_resp = client.get(f"{base}/steps")
    exec_resp = client.get(f"{base}/execution")
    arts_resp = client.get(f"{base}/artifacts")
    steps = steps_resp.json().get("items") or [] if steps_resp.status_code == 200 else []
    execution = exec_resp.json() if exec_resp.status_code == 200 else {}
    artifacts = arts_resp.json().get("items") or [] if arts_resp.status_code == 200 else []
    return steps, execution, artifacts


# --------------------------------------------------------------------------- #
# Verification (Gate B) — every check must be evidence-based
# --------------------------------------------------------------------------- #


def verify_run(
    task: dict[str, Any],
    steps: list[dict[str, Any]],
    execution: dict[str, Any],
    artifacts: list[dict[str, Any]],
    *,
    expect_llm: bool,
) -> list[tuple[str, bool, str]]:
    result = task.get("result_json") or {}
    preview = result.get("table_preview") or {}
    charts = result.get("charts") or []
    report = result.get("report") or {}
    llm_steps = [
        (s.get("node_name"), (s.get("output_json") or {}).get("llm") or {})
        for s in steps
        if isinstance((s.get("output_json") or {}).get("llm"), dict)
    ]
    heuristic_steps = [n for n, m in llm_steps if m.get("mode") == "heuristic" or m.get("status") == "skipped"]
    ok_steps = [
        (n, m)
        for n, m in llm_steps
        if m.get("status") == "ok" and int((m.get("usage") or {}).get("total_tokens") or 0) > 0
    ]

    checks: list[tuple[str, bool, str]] = [
        ("task.status == succeeded", task.get("status") == "succeeded", str(task.get("status"))),
        ("result_json.sql 非空", bool(result.get("sql")), (str(result.get("sql"))[:80] or "<empty>")),
        (
            "table_preview 有数据行",
            bool(preview.get("rows")),
            f"rows={len(preview.get('rows') or [])} cols={len(preview.get('columns') or [])}",
        ),
        ("charts 非空", bool(charts), f"count={len(charts)} types={[c.get('type') for c in charts][:3]}"),
        ("report.markdown 非空", bool(report.get("markdown")), str(report.get("title") or "<no title>")),
        (
            "execution.tool_calls 非空",
            bool((execution.get("execution") or {}).get("tool_calls")),
            f"tool_calls={len((execution.get('execution') or {}).get('tool_calls') or [])}",
        ),
        (
            "execution.policy_decisions 非空",
            bool((execution.get("execution") or {}).get("policy_decisions")),
            f"policy_decisions={len((execution.get('execution') or {}).get('policy_decisions') or [])}",
        ),
        (
            "execution.artifacts 非空",
            bool((execution.get("execution") or {}).get("artifacts")),
            f"artifacts={len((execution.get('execution') or {}).get('artifacts') or [])}",
        ),
        (
            "artifacts API 返回产物",
            bool(artifacts),
            f"count={len(artifacts)} types={sorted({a.get('type') for a in artifacts})}",
        ),
    ]

    llm_ok = bool(ok_steps) and not heuristic_steps
    checks.append(
        (
            "LLM 调用为真实调用(status=ok 且 usage.total_tokens>0)",
            llm_ok,
            (
                f"ok_steps={[n for n, _ in ok_steps]} "
                f"heuristic_steps={heuristic_steps} "
                f"tokens={[ (m.get('usage') or {}).get('total_tokens') for _, m in ok_steps ]}"
            ),
        )
    )
    checks.append(
        (
            "llm_total_tokens > 0",
            int(task.get("llm_total_tokens") or 0) > 0,
            f"llm_total_tokens={task.get('llm_total_tokens')}",
        )
    )
    if expect_llm:
        checks.append(
            (
                "--expect-llm: 未走 heuristic 回退",
                not heuristic_steps,
                f"heuristic_steps={heuristic_steps or 'none'}",
            )
        )
    return checks


def print_checks(checks: list[tuple[str, bool, str]]) -> bool:
    print("\n================= Gate B 断言结果 =================")
    width = max(len(name) for name, _, _ in checks)
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name.ljust(width)}  {detail}")
    failed = [name for name, ok, _ in checks if not ok]
    print("===================================================")
    if failed:
        print(f"FAILED: {len(failed)}/{len(checks)} 项未通过 -> {failed}")
        return False
    print(f"ALL PASSED: {len(checks)}/{len(checks)}")
    return True


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Phase 1 demo bootstrap (real HTTP API, no shortcuts).")
    p.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    p.add_argument("--email", default="demo@example.com")
    p.add_argument("--password", default="DemoPass123!")
    p.add_argument("--display-name", default="Demo User")
    p.add_argument("--dataset-name", default="Demo Postgres RO (orders/customers)")
    p.add_argument("--ask", default=None, help="optional question to run end-to-end")
    p.add_argument("--timeout", type=float, default=180.0, help="seconds to wait for a run")
    p.add_argument("--poll-interval", type=float, default=2.0)
    p.add_argument(
        "--expect-llm",
        action="store_true",
        help="fail if the run fell back to heuristic SQL (proves a real LLM was used)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        try:
            health = client.get("/health/ready")
            if health.status_code != 200:
                _fail(health, "GET /health/ready (is the stack up?)")
            print(f"[ok]  API ready at {args.base_url}")
        except httpx.HTTPError as exc:
            print(f"FAIL: cannot reach {args.base_url}: {exc}", file=sys.stderr)
            return 1

        try:
            auth = register_or_login(
                client, email=args.email, password=args.password, display=args.display_name
            )
            token = auth["access_token"]
            client.headers["Authorization"] = f"Bearer {token}"

            workspace_id = resolve_workspace(client, auth)
            dataset = ensure_postgres_ro_dataset(
                client, workspace_id=workspace_id, name=args.dataset_name
            )

            question = args.ask or DEFAULT_QUESTION
            if not args.ask:
                print(f"\n[--] 未指定 --ask，跳过端到端提问。可用 dataset_id={dataset['id']}")
                print(f"[--] 试用: --ask \"{DEFAULT_QUESTION}\"")
                return 0

            print(f"\n[..]  question: {question}")
            task = create_task(
                client, workspace_id=workspace_id, dataset_id=str(dataset["id"]), question=question
            )
            final = poll_task(
                client,
                workspace_id=workspace_id,
                task_id=str(task["id"]),
                timeout=args.timeout,
                interval=args.poll_interval,
            )
            steps, execution, artifacts = fetch_run_details(
                client, workspace_id=workspace_id, task_id=str(task["id"])
            )
            print(f"[ok]  steps={len(steps)} artifacts={len(artifacts)}")
            if final.get("error_message"):
                print(f"[!!]  error_message: {final['error_message']}")
            if final.get("failure_class"):
                print(f"[!!]  failure_class: {final['failure_class']}")

            checks = verify_run(final, steps, execution, artifacts, expect_llm=args.expect_llm)
            passed = print_checks(checks)
            if not passed:
                # Any failed assertion must surface as a non-zero exit code,
                # even when the Run itself succeeded (e.g. --expect-llm caught a
                # heuristic fallback). Never mask a verification failure as success.
                return 2
            return 0
        except DemoError as exc:
            print(f"\nFAIL: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
