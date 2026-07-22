"""Release gate: alembic head + curated smokes (DH.3).

M3 smoke runs only when POSTGRES_RO_DSN is set.
P0-1 eval core suite always runs (heuristic forced off; baseline compare if present).
E1-AC schema linking smoke + quality eval suite always run (deterministic).
Does not start API/Worker — operator must have Compose deps up.

Usage (from backend/):
  .\\.venv\\Scripts\\python.exe scripts\\smoke_release_gate.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
PYTHON = sys.executable


def _run(label: str, args: list[str], *, env: dict | None = None) -> None:
    print(f"\n=== {label} ===")
    merged = os.environ.copy()
    if env:
        merged.update(env)
    proc = subprocess.run(
        args,
        cwd=str(BACKEND),
        env=merged,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"GATE FAIL: {label} (exit {proc.returncode})")
    print(f"OK: {label}")


def main() -> None:
    print("Release gate starting")
    print(f"python={PYTHON}")
    print(f"backend={BACKEND}")

    _run(
        "alembic upgrade head",
        [PYTHON, "-m", "alembic", "upgrade", "head"],
    )

    core = [
        ("smoke_kernel_m1", ["scripts/smoke_kernel_m1.py"]),
        ("smoke_skill_lifecycle", ["scripts/smoke_skill_lifecycle.py"]),
        ("smoke_data_profile", ["scripts/smoke_data_profile.py"]),
        ("smoke_wave3_platform", ["scripts/smoke_wave3_platform.py"]),
        ("smoke_task_events", ["scripts/smoke_task_events.py"]),
        ("smoke_docker_compose", ["scripts/smoke_docker_compose.py"]),
        ("smoke_m2_lifecycle", ["scripts/smoke_m2_lifecycle.py"]),
        ("smoke_p1_1_cooperative_cancel", ["scripts/smoke_p1_1_cooperative_cancel.py"]),
        ("smoke_m4_execution_trace", ["scripts/smoke_m4_execution_trace.py"]),
        ("smoke_m5_permissions", ["scripts/smoke_m5_permissions.py"]),
        ("smoke_p1_permissions", ["scripts/smoke_p1_permissions.py"]),
        ("smoke_e2_explainability", ["scripts/smoke_e2_explainability.py"]),
        ("smoke_m6_artifacts", ["scripts/smoke_m6_artifacts.py"]),
        ("smoke_e3_runtime_essentials", ["scripts/smoke_e3_runtime_essentials.py"]),
        ("smoke_sql_prompt", ["scripts/smoke_sql_prompt.py"]),
        ("smoke_auth_refresh", ["scripts/smoke_auth_refresh.py"]),
        ("smoke_rate_limit", ["scripts/smoke_rate_limit.py"]),
        ("smoke_config_hardening", ["scripts/smoke_config_hardening.py"]),
        ("smoke_metrics", ["scripts/smoke_metrics.py"]),
        ("smoke_openapi_contract", ["scripts/smoke_openapi_contract.py"]),
        ("smoke_repair_classify", ["scripts/smoke_repair_classify.py"]),
    ]
    for label, rel in core:
        _run(label, [PYTHON, *rel])

    dsn = (os.environ.get("POSTGRES_RO_DSN") or "").strip()
    if dsn:
        _run(
            "smoke_m3_connector (POSTGRES_RO_DSN set)",
            [PYTHON, "scripts/smoke_m3_connector.py"],
        )
    else:
        print("\n=== smoke_m3_connector ===")
        print("SKIP: POSTGRES_RO_DSN unset (file/core path gate unaffected)")

    # P0-2 Soft Cost Budget (default budget 0; smoke forces env budget)
    _run("smoke_p0_2_cost_budget", [PYTHON, "scripts/smoke_p0_2_cost_budget.py"])

    # E1-A Schema Linking Lite
    _run("smoke_schema_linking", [PYTHON, "scripts/smoke_schema_linking.py"])

    # P0-1: AI quality gate (deterministic core suite; heuristic forced off)
    baseline = REPO / "evals" / "baselines" / "core_latest.json"
    eval_args = [
        PYTHON,
        "scripts/smoke_eval_golden.py",
        "--suite",
        "core",
        "--report",
        str(REPO / "evals" / "reports" / "core_gate.json"),
    ]
    if baseline.is_file():
        eval_args.extend(["--fail-on-regression", str(baseline)])
    _run("smoke_eval_golden (core)", eval_args)

    # E1-C: Schema Linking / Eval Quality suite (deterministic)
    q_baseline = REPO / "evals" / "baselines" / "quality_latest.json"
    quality_args = [
        PYTHON,
        "scripts/smoke_eval_golden.py",
        "--suite",
        "quality",
        "--report",
        str(REPO / "evals" / "reports" / "quality_gate.json"),
    ]
    if q_baseline.is_file():
        quality_args.extend(["--fail-on-regression", str(q_baseline)])
    _run("smoke_eval_golden (quality)", quality_args)

    # Wave 3: second Skill eval suite (no baseline gate yet — prove Kernel extensibility)
    _run(
        "smoke_eval_golden (profile)",
        [
            PYTHON,
            "scripts/smoke_eval_golden.py",
            "--suite",
            "profile",
            "--report",
            str(REPO / "evals" / "reports" / "profile_gate.json"),
        ],
    )

    print("\nRELEASE GATE PASS")


if __name__ == "__main__":
    main()
