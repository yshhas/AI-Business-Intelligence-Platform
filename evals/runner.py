"""P0-1 Eval runner library — public API entry point.

Internal modules: _models, _scorers, _fixtures, _executors, _reporter.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evals._executors import run_case
from evals._models import CaseResult, CheckResult
from evals._reporter import _summarize, compare_baseline, write_report

__all__ = [
    "RUNNER_VERSION",
    "evals_root",
    "load_suite",
    "run_suite",
    "CaseResult",
    "CheckResult",
    "compare_baseline",
    "write_report",
]

RUNNER_VERSION = 1
EVALS_ROOT = Path(__file__).resolve().parent


def evals_root() -> Path:
    return EVALS_ROOT


def load_suite(suite: str) -> dict[str, Any]:
    path = EVALS_ROOT / "suites" / suite / "cases.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Suite not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "cases" not in data:
        raise ValueError(f"Invalid suite file: {path}")
    return data


def run_suite(suite: str) -> dict[str, Any]:
    data = load_suite(suite)
    defaults = dict(data.get("defaults") or {})
    # Force heuristic off at suite level
    defaults["allow_heuristic_sql"] = False
    started = datetime.now(UTC).isoformat()
    results: list[CaseResult] = []
    for case in data.get("cases") or []:
        if not isinstance(case, dict) or not case.get("id"):
            continue
        results.append(run_case(case, defaults))
    finished = datetime.now(UTC).isoformat()
    summary = _summarize(results)
    llm_enabled = bool((os.environ.get("LLM_API_KEY") or "").strip())
    return {
        "suite": suite,
        "suite_version": data.get("version", 1),
        "runner_version": RUNNER_VERSION,
        "started_at": started,
        "finished_at": finished,
        "config": {
            "allow_heuristic_sql": False,
            "llm_enabled": llm_enabled,
            "skill_id": defaults.get("skill_id", "data.bi"),
            "postgres_ro": bool((os.environ.get("POSTGRES_RO_DSN") or "").strip()),
        },
        "summary": summary,
        "cases": [r.as_dict() for r in results],
    }