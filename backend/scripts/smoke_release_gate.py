"""Release gate: alembic head + curated smokes (DH.3).

M3 smoke runs only when POSTGRES_RO_DSN is set.
P0-1 eval core suite always runs (heuristic forced off; baseline compare if present).
E1-AC schema linking smoke + quality eval suite always run (deterministic).
HITL: H1 + H2 (T1–T5) always run (capacity reset between H2 smokes).
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

# HITL H2 order is intentional: approve API → resume CAS → execute → mock → snapshot
HITL_H2_SMOKES: list[tuple[str, str]] = [
    ("hitl_h2/t1_approve_api", "scripts/smoke_hitl_h2_t1_approve_api.py"),
    ("hitl_h2/t2_resume_cas", "scripts/smoke_hitl_h2_t2_resume_cas.py"),
    ("hitl_h2/t3_execute", "scripts/smoke_hitl_h2_t3_execute.py"),
    ("hitl_h2/t4_mock_runtime", "scripts/smoke_hitl_h2_t4_mock_runtime.py"),
    ("hitl_h2/t5_snapshot", "scripts/smoke_hitl_h2_t5_snapshot.py"),
]


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
        raise SystemExit(
            f"GATE FAIL: stage={label} exit={proc.returncode} "
            f"cmd={' '.join(args)}"
        )
    print(f"OK: {label}")


def _reset_hitl_smoke_capacity(*, before_stage: str) -> None:
    """Clear in-flight leftovers between HITL H2 smokes (does not change smoke scripts).

    H2 smokes park/awaiting or briefly run; without reset, later smokes hit
    run_max_in_flight and fail as pending — false negatives in the gate.
    """
    print(f"\n=== hitl_capacity_reset (before {before_stage}) ===")
    code = r"""
from datetime import UTC, datetime
from sqlalchemy import or_, update
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import AnalysisTask
from app.services import queue as q
from app.services import run_lifecycle as rl
from app.services import runtime_essentials as rt

db = SessionLocal()
try:
    s = get_settings()
    now = datetime.now(UTC)
    db.execute(
        update(AnalysisTask)
        .where(
            or_(
                AnalysisTask.status == "running",
                AnalysisTask.status == rl.STATUS_AWAITING_APPROVAL,
            )
        )
        .values(
            status="failed",
            failure_class="internal_error",
            error_message="release_gate: HITL smoke capacity reset",
            finished_at=now,
            hitl_resume_requested=False,
        )
    )
    db.commit()
    r = q.get_redis()
    r.delete(s.hitl_resume_queue_key, s.analysis_queue_key)
    print(f"inflight_after={rt.count_running(db)}")
finally:
    db.close()
"""
    proc = subprocess.run(
        [PYTHON, "-c", code],
        cwd=str(BACKEND),
        env=os.environ.copy(),
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"GATE FAIL: stage=hitl_capacity_reset before={before_stage} "
            f"exit={proc.returncode}"
        )
    print(f"OK: hitl_capacity_reset (before {before_stage})")


def _run_hitl_h2_suite() -> None:
    print("\n========== HITL H2 suite (T1→T5) ==========")
    for label, rel in HITL_H2_SMOKES:
        _reset_hitl_smoke_capacity(before_stage=label)
        _run(label, [PYTHON, rel])
    _reset_hitl_smoke_capacity(before_stage="hitl_h2/complete")
    print("OK: HITL H2 suite complete")


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
        ("smoke_list_tasks_nplus1", ["scripts/smoke_list_tasks_nplus1.py"]),
        ("smoke_result_payload", ["scripts/smoke_result_payload.py"]),
        ("smoke_hitl_h1", ["scripts/smoke_hitl_h1.py"]),
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

    # HITL H2 — after H1 (in core); ordered T1→T5 with capacity isolation
    _run_hitl_h2_suite()

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
