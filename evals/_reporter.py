"""Eval reporter — summary, baseline comparison, and JSON report writing."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals._models import CaseResult


def _summarize(results: list[CaseResult]) -> dict[str, Any]:
    scored = [r for r in results if not r.skipped]
    total = len(scored)
    passed = sum(1 for r in scored if r.passed)
    failed = total - passed

    def _rate(predicate) -> float | None:
        subset = [r for r in scored if predicate(r)]
        if not subset:
            return None
        return round(sum(1 for r in subset if r.passed) / len(subset), 4)

    gate_cases = [
        r
        for r in scored
        if r.checks.get("gate") in {"pass", "fail"}
    ]
    exec_cases = [r for r in scored if r.checks.get("execute") in {"pass", "fail"}]
    result_cases = [r for r in scored if r.checks.get("result") in {"pass", "fail"}]
    result_checks_cases = [r for r in scored if r.checks.get("result_checks") in {"pass", "fail"}]

    fc_dist: dict[str, int] = {}
    for r in scored:
        fc = r.observed.get("failure_class")
        key = "none" if fc is None else str(fc)
        fc_dist[key] = fc_dist.get(key, 0) + 1

    heuristic_use = sum(1 for r in scored if r.observed.get("heuristic_used"))

    link_aware = [r for r in scored if r.observed.get("link_status") is not None]
    link_dist: dict[str, int] = {}
    for r in link_aware:
        key = str(r.observed.get("link_status"))
        link_dist[key] = link_dist.get(key, 0) + 1
    link_n = len(link_aware)
    link_ok_rate = (
        round(sum(1 for r in link_aware if r.observed.get("link_status") == "ok") / link_n, 4)
        if link_n
        else None
    )
    link_fallback_rate = (
        round(
            sum(1 for r in link_aware if r.observed.get("link_status") == "fallback_full") / link_n,
            4,
        )
        if link_n
        else None
    )
    link_failed_rate = (
        round(
            sum(1 for r in link_aware if r.observed.get("link_status") == "failed") / link_n,
            4,
        )
        if link_n
        else None
    )
    schema_link_passed = sum(1 for r in link_aware if r.passed)

    # E2E pipeline metrics
    pipeline_cases = [r for r in scored if r.observed.get("sql_source") in ("llm", "heuristic")]
    e2e_success_rate = (
        round(sum(1 for r in pipeline_cases if r.observed.get("success")) / len(pipeline_cases), 4)
        if pipeline_cases
        else None
    )
    sql_gen_pass_rate = (
        round(
            sum(1 for r in pipeline_cases if r.observed.get("sql_final") is not None)
            / len(pipeline_cases),
            4,
        )
        if pipeline_cases
        else None
    )
    # Gate safety: deny cases correctly denied
    gate_deny_cases = [r for r in gate_cases if not r.observed.get("gate_ok")]
    gate_safety_pass_rate = (
        round(
            sum(1 for r in gate_deny_cases if r.checks.get("gate") == "pass") / len(gate_deny_cases),
            4,
        )
        if gate_deny_cases
        else None
    )

    # Safety metrics: attack cases blocked, regression tracking
    attack_cases = [r for r in scored if r.observed.get("tags") and "attack" in r.observed.get("tags", [])]
    blocked_attack_count = sum(1 for r in attack_cases if r.checks.get("gate") == "pass")
    safety_pass_rate = (
        round(blocked_attack_count / len(attack_cases), 4) if attack_cases else None
    )
    regression_cases = [r for r in scored if r.observed.get("tags") and "regression" in r.observed.get("tags", [])]
    regression_pass_count = sum(1 for r in regression_cases if r.passed)

    # ── Repair metrics ──────────────────────────────────────────────────
    repair_cases = [
        r for r in scored
        if r.observed.get("tags") and "repair" in r.observed.get("tags", [])
    ]
    repair_total = len(repair_cases)

    # Cases where retry actually happened (retry_count > 0)
    repair_triggered = [
        r for r in repair_cases
        if (r.observed.get("retry_count") or 0) > 0
    ]
    repair_triggered_count = len(repair_triggered)

    # repair_success_rate: among cases where retry was triggered, how many succeeded
    repair_success_count = sum(
        1 for r in repair_triggered
        if r.observed.get("success")
    )
    repair_success_rate = (
        round(repair_success_count / repair_triggered_count, 4)
        if repair_triggered_count
        else None
    )

    # repair_triggered_rate: how often repair was needed
    repair_triggered_rate = (
        round(repair_triggered_count / repair_total, 4) if repair_total else None
    )

    # repair_by_class: success rate per repair_class (only for retry-triggered cases)
    repair_by_class: dict[str, dict[str, int]] = {}
    for r in repair_triggered:
        rc = r.observed.get("repair_class") or "unknown"
        if rc not in repair_by_class:
            repair_by_class[rc] = {"total": 0, "success": 0}
        repair_by_class[rc]["total"] += 1
        if r.observed.get("success"):
            repair_by_class[rc]["success"] += 1
    repair_by_class_rate: dict[str, float] = {}
    for rc, counts in repair_by_class.items():
        if counts["total"] > 0:
            repair_by_class_rate[rc] = round(counts["success"] / counts["total"], 4)

    # repair_attempt_success_rate: success rate by attempt N
    attempt_success: dict[int, dict[str, int]] = {}
    for r in repair_triggered:
        rc = r.observed.get("retry_count") or 0
        if rc > 0:
            if rc not in attempt_success:
                attempt_success[rc] = {"total": 0, "success": 0}
            attempt_success[rc]["total"] += 1
            if r.observed.get("success"):
                attempt_success[rc]["success"] += 1
    repair_attempt_success_rate: dict[int, float] = {}
    for attempt, counts in attempt_success.items():
        if counts["total"] > 0:
            repair_attempt_success_rate[attempt] = round(
                counts["success"] / counts["total"], 4
            )

    # max_retry_exceeded_rate: among triggered cases, how many exceeded max_retries
    max_retry_failed = sum(
        1 for r in repair_triggered
        if (r.observed.get("retry_count") or 0) >= 2
        and not r.observed.get("success")
    )
    max_retry_exceeded_rate = (
        round(max_retry_failed / repair_triggered_count, 4)
        if repair_triggered_count
        else None
    )

    # Non-repairable denial rate: how many repair cases were correctly denied (security)
    repair_denied = [
        r for r in repair_cases
        if (r.observed.get("retry_count") or 0) == 0
        and not r.observed.get("success")
        and r.observed.get("repair_class") == "policy_keyword"
    ]
    repair_denied_rate = (
        round(len(repair_denied) / repair_total, 4) if repair_total else None
    )

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": sum(1 for r in results if r.skipped),
        "gate_pass_rate": round(
            sum(1 for r in gate_cases if r.checks.get("gate") == "pass") / len(gate_cases), 4
        )
        if gate_cases
        else None,
        "execute_success_rate": round(
            sum(1 for r in exec_cases if r.checks.get("execute") == "pass") / len(exec_cases), 4
        )
        if exec_cases
        else None,
        "result_match_rate": round(
            sum(1 for r in result_cases if r.checks.get("result") == "pass") / len(result_cases), 4
        )
        if result_cases
        else None,
        "result_accuracy_rate": round(
            sum(1 for r in result_checks_cases if r.checks.get("result_checks") == "pass")
            / len(result_checks_cases),
            4,
        )
        if result_checks_cases
        else None,
        "result_checks_cases": len(result_checks_cases),
        "outcome_success_rate": round(passed / total, 4) if total else None,
        "failure_class_distribution": fc_dist,
        "heuristic_use_count": heuristic_use,
        "case_pass_rate": _rate(lambda _r: True),
        "link_status_distribution": link_dist,
        "link_ok_rate": link_ok_rate,
        "link_fallback_rate": link_fallback_rate,
        "link_failed_rate": link_failed_rate,
        "schema_link_cases": link_n,
        "schema_link_passed": schema_link_passed,
        # E2E metrics
        "e2e_success_rate": e2e_success_rate,
        "sql_gen_pass_rate": sql_gen_pass_rate,
        "gate_safety_pass_rate": gate_safety_pass_rate,
        "pipeline_cases": len(pipeline_cases),
        # Safety metrics
        "safety_pass_rate": safety_pass_rate,
        "blocked_attack_count": blocked_attack_count,
        "total_attack_cases": len(attack_cases),
        "regression_cases": len(regression_cases),
        "regression_pass_count": regression_pass_count,
        # Repair metrics
        "repair_cases": repair_total,
        "repair_triggered_count": repair_triggered_count,
        "repair_success_count": repair_success_count,
        "repair_success_rate": repair_success_rate,
        "repair_triggered_rate": repair_triggered_rate,
        "repair_by_class": repair_by_class_rate,
        "repair_attempt_success_rate": repair_attempt_success_rate,
        "max_retry_exceeded_rate": max_retry_exceeded_rate,
        "repair_denied_rate": repair_denied_rate,
    }


def compare_baseline(report: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    """Return list of regression messages (empty = OK)."""
    regressions: list[str] = []
    base_cases = {c["id"]: c for c in baseline.get("cases") or [] if not c.get("skipped")}
    cur_by_id = {c["id"]: c for c in report.get("cases") or []}

    for cid, prev in base_cases.items():
        if not prev.get("passed"):
            continue
        cur = cur_by_id.get(cid)
        if cur is None:
            regressions.append(f"missing case {cid!r} (was pass)")
        elif cur.get("skipped"):
            # Environment-conditional skip (e.g. POSTGRES_RO_DSN) is not a regression
            continue
        elif not cur.get("passed"):
            regressions.append(f"regressed {cid!r}: was pass, now fail {cur.get('errors')}")

    bsum = baseline.get("summary") or {}
    csum = report.get("summary") or {}
    for key in (
        "gate_pass_rate",
        "execute_success_rate",
        "result_match_rate",
        "outcome_success_rate",
        "link_ok_rate",
        "schema_link_passed",
    ):
        bv, cv = bsum.get(key), csum.get(key)
        if bv is None or cv is None:
            continue
        if float(cv) + 1e-9 < float(bv):
            regressions.append(f"rate {key} dropped {bv} → {cv}")

    # Rising failed/fallback rates are quality regressions (do not hide fallback)
    for key in ("link_failed_rate",):
        bv, cv = bsum.get(key), csum.get(key)
        if bv is None or cv is None:
            continue
        if float(cv) > float(bv) + 1e-9:
            regressions.append(f"rate {key} rose {bv} → {cv}")

    if int(csum.get("heuristic_use_count") or 0) > 0:
        regressions.append("heuristic_use_count > 0")

    return regressions


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")