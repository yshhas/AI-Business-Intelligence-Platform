"""Eval case executors — SQL inject, Schema Linking, Pipeline, Repair Mock.

Each executor runs a single case and returns a CaseResult.
"""

from __future__ import annotations

import os
import time
from typing import Any
from uuid import uuid4

from evals._fixtures import _execute_file, _execute_postgres, _prepare_file_fixture
from evals._models import CaseResult
from evals._scorers import (
    _detect_heuristic,
    _map_failure_class,
    _score_link_expects,
    _score_result_checks,
    _score_row_checks,
    _score_sql_constraints,
    _subst,
)


def _extract_link_from_steps(steps: list[Any]) -> dict[str, Any]:
    for step in reversed(steps or []):
        if getattr(step, "node_name", None) != "link_schema":
            continue
        out = getattr(step, "output_json", None) or {}
        if not isinstance(out, dict):
            return {}
        return {
            "link_status": out.get("link_status"),
            "link_method": out.get("link_method"),
            "link_reason": out.get("link_reason"),
            "selected_tables": list(out.get("selected_tables") or []),
            "selected_columns": list(out.get("selected_columns") or []),
            "column_count_full": out.get("column_count_full"),
            "column_count_linked": out.get("column_count_linked"),
        }
    return {}


def _extract_repair_from_steps(steps: list[Any]) -> dict[str, Any]:
    """Extract repair_history, retry_count, and repair_class from pipeline steps."""
    repair_history: list[dict[str, Any]] = []
    retry_count = 0
    repair_class: str | None = None

    for step in steps or []:
        out = getattr(step, "output_json", None) or {}
        if not isinstance(out, dict):
            continue
        node_name = getattr(step, "node_name", "") or ""
        # Prefer summarize step's repair_history (full state snapshot)
        if node_name == "summarize" and "repair_history" in out:
            repair_history = list(out["repair_history"])
            retry_count = int(out.get("retry_count") or 0)
            continue
        # Collect repair_class from validate_sql / execute_sql errors
        rc = out.get("repair_class")
        if rc and not repair_class:
            repair_class = str(rc)

    # Fallback: count error steps if no summarize data
    if not repair_history:
        for step in steps or []:
            node_name = getattr(step, "node_name", "") or ""
            status = getattr(step, "status", "") or ""
            if node_name in {"validate_sql", "execute_sql"} and status == "error":
                retry_count += 1
                out = getattr(step, "output_json", None) or {}
                if isinstance(out, dict):
                    rc = out.get("repair_class")
                    if rc and not repair_class:
                        repair_class = str(rc)

    return {
        "repair_history": repair_history,
        "retry_count": retry_count,
        "repair_class": repair_class,
    }


# ── SQL Inject executor ─────────────────────────────────────────────────


def _run_sql_inject(case: dict[str, Any], defaults: dict[str, Any]) -> CaseResult:
    from agent.kernel.policies import apply_sql_select_gate
    from agent.repair_classify import classify_repair_error

    cid = str(case["id"])
    plane = str(case.get("plane") or defaults.get("plane") or "file")
    default_limit = int(case.get("default_limit") or defaults.get("default_limit") or 200)
    expect = case.get("expect") or {}
    executed = False
    preview: dict[str, Any] | None = None
    errors: list[str] = []
    checks: dict[str, str] = {}

    if case.get("require_postgres_ro") and not (os.environ.get("POSTGRES_RO_DSN") or "").strip():
        return CaseResult(
            id=cid,
            passed=True,
            skipped=True,
            skip_reason="POSTGRES_RO_DSN unset",
            checks={"skip": "pass"},
            observed={},
        )

    workspace_id = uuid4()
    table = str(case.get("table") or "")
    schema: list[dict[str, str]] = []
    allowed: set[str]

    if plane == "file":
        fixture = str(case.get("fixture") or defaults.get("fixture") or "fixtures/file/sales_mini.csv")
        table, schema, _rc = _prepare_file_fixture(fixture_rel=fixture, workspace_id=workspace_id)
        allowed = {table}
    elif plane == "postgres_ro":
        if not table:
            table = "public.demo_orders"
        allowed_list = case.get("allowed_tables") or [table]
        allowed = {str(t) for t in allowed_list}
    else:
        return CaseResult(id=cid, passed=False, errors=[f"unknown plane {plane!r}"])

    raw_sql = _subst(str(case.get("sql") or ""), table=table)
    gate, decision = apply_sql_select_gate(
        raw_sql,
        allowed_tables=allowed,
        default_limit=default_limit,
    )

    expect_gate = str(expect.get("gate") or "").lower()
    if expect_gate == "allow":
        checks["gate"] = "pass" if gate.ok else "fail"
        if not gate.ok:
            errors.append(f"expected allow, gate denied: {gate.error}")
    elif expect_gate == "deny":
        checks["gate"] = "pass" if not gate.ok else "fail"
        if gate.ok:
            errors.append("expected deny, gate allowed")
    else:
        checks["gate"] = "pass" if True else "fail"

    sql_final = gate.sql if gate.ok else None
    sql_check = _score_sql_constraints(
        sql_final or raw_sql,
        expect.get("sql_constraints"),
        table=table,
    )
    checks["sql_constraints"] = "pass" if sql_check.ok else "fail"
    if not sql_check.ok and expect.get("sql_constraints"):
        errors.append(sql_check.detail)

    want_execute = bool(case.get("execute")) and gate.ok
    if expect.get("must_not_execute"):
        if want_execute:
            errors.append("must_not_execute but execute requested on allow")
        checks["execute"] = "pass"  # correctly did not execute
    elif want_execute:
        try:
            if plane == "file":
                preview = _execute_file(
                    workspace_id=workspace_id,
                    sql=raw_sql,
                    table=table,
                    default_limit=default_limit,
                )
            else:
                preview = _execute_postgres(
                    sql=raw_sql,
                    allowed_tables=allowed,
                    default_limit=default_limit,
                )
            executed = True
            checks["execute"] = "pass"
            sql_final = preview.get("sql") or sql_final
        except Exception as exc:  # noqa: BLE001
            checks["execute"] = "fail"
            errors.append(f"execute failed: {exc}")
    else:
        checks["execute"] = "skip" if not gate.ok else "skip"

    row_check = _score_row_checks(preview, expect.get("row_checks"))
    if expect.get("row_checks"):
        checks["result"] = "pass" if row_check.ok else "fail"
        if not row_check.ok:
            errors.append(row_check.detail)
    else:
        checks["result"] = "skip"

    result_check = _score_result_checks(preview, expect.get("result_checks"))
    if expect.get("result_checks"):
        checks["result_checks"] = "pass" if result_check.ok else "fail"
        if not result_check.ok:
            errors.append(result_check.detail)
    else:
        checks["result_checks"] = "skip"

    success = bool(gate.ok and (executed if case.get("execute") else gate.ok) and not errors)
    # Recompute success from expect.success if present
    if "success" in expect:
        expected_success = bool(expect["success"])
        # For deny cases success is false even when checks pass
        observed_success = gate.ok and (executed if case.get("execute") else True) and (
            checks.get("execute") != "fail"
        )
        if expect_gate == "deny":
            observed_success = False
        checks["success"] = "pass" if observed_success == expected_success else "fail"
        if observed_success != expected_success:
            errors.append(f"success expected {expected_success}, got {observed_success}")
        success = observed_success
    else:
        success = gate.ok if not case.get("execute") else (gate.ok and executed)

    failure_class = _map_failure_class(
        gate_ok=gate.ok,
        success=success if expect_gate != "deny" else False,
        error_message=gate.error,
        result_json=None,
        executed=executed,
    )
    if "failure_class" in expect:
        want_fc = expect["failure_class"]
        # null in YAML → None
        if want_fc is None or want_fc == "none":
            ok_fc = failure_class is None
        else:
            ok_fc = failure_class == want_fc
        checks["failure_class"] = "pass" if ok_fc else "fail"
        if not ok_fc:
            errors.append(f"failure_class expected {want_fc!r}, got {failure_class!r}")
    else:
        checks["failure_class"] = "skip"

    passed = not errors and all(v != "fail" for v in checks.values())
    return CaseResult(
        id=cid,
        passed=passed,
        checks=checks,
        observed={
            "success": success if expect_gate != "deny" else False,
            "sql_final": sql_final,
            "sql_raw": raw_sql,
            "gate_ok": gate.ok,
            "gate_reason": gate.error,
            "policy_id": decision.policy_id,
            "failure_class": failure_class,
            "repair_class": classify_repair_error(gate.error, stage="validate"),
            "row_count": (preview or {}).get("row_count"),
            "executed": executed,
            "plane": plane,
            "table": table,
            "sql_source": "injected",
            "heuristic_used": False,
            "tags": case.get("tags") or [],
        },
        errors=errors,
    )


# ── Schema Linking executor ─────────────────────────────────────────────


def _run_link_only(case: dict[str, Any], defaults: dict[str, Any]) -> CaseResult:
    """Deterministic Schema Linking Lite — no LLM / Gate / Plane."""
    from agent.schema_linking import link_schema as run_link

    cid = str(case["id"])
    expect = case.get("expect") or {}
    question = str(case.get("question") or "")
    table = str(case.get("table") or "ds_eval")
    max_columns = int(
        case.get("max_columns")
        or defaults.get("max_columns")
        or defaults.get("schema_link_max_columns")
        or 12
    )
    allowed = [str(t) for t in (case.get("allowed_tables") or [table])]

    schema: list[dict[str, Any]]
    if "schema" in case:
        raw = case.get("schema") or []
        schema = [dict(c) for c in raw if isinstance(c, dict)]
    else:
        workspace_id = uuid4()
        fixture = str(case.get("fixture") or defaults.get("fixture") or "fixtures/file/sales_mini.csv")
        try:
            table, schema, _rc = _prepare_file_fixture(fixture_rel=fixture, workspace_id=workspace_id)
            allowed = [table]
        except Exception as exc:  # noqa: BLE001
            return CaseResult(id=cid, passed=False, errors=[str(exc)])

    result = run_link(
        question=question,
        schema=schema,
        table=table,
        allowed_tables=allowed,
        max_columns=max_columns,
    )
    checks, errors = _score_link_expects(
        link_status=result.link_status,
        link_method=result.link_method,
        selected_columns=result.selected_columns,
        selected_tables=result.selected_tables,
        expect=expect,
        table=table,
    )
    if not checks:
        checks["link"] = "pass"

    passed = not errors and all(v != "fail" for v in checks.values())
    return CaseResult(
        id=cid,
        passed=passed,
        checks=checks,
        observed={
            "link_status": result.link_status,
            "link_method": result.link_method,
            "link_reason": result.link_reason,
            "selected_tables": result.selected_tables,
            "selected_columns": result.selected_columns,
            "column_count_full": result.column_count_full,
            "column_count_linked": result.column_count_linked,
            "table": table,
            "heuristic_used": False,
            "sql_source": "none",
        },
        errors=errors,
    )


# ── Fixture Meta executor ───────────────────────────────────────────────


def _run_fixture_meta(case: dict[str, Any], defaults: dict[str, Any]) -> CaseResult:
    cid = str(case["id"])
    expect = case.get("expect") or {}
    workspace_id = uuid4()
    fixture = str(case.get("fixture") or defaults.get("fixture") or "fixtures/file/sales_mini.csv")
    errors: list[str] = []
    checks: dict[str, str] = {}
    try:
        table, schema, row_count = _prepare_file_fixture(fixture_rel=fixture, workspace_id=workspace_id)
    except Exception as exc:  # noqa: BLE001
        return CaseResult(id=cid, passed=False, errors=[str(exc)])

    if "fixture_row_count" in expect:
        ok = row_count == int(expect["fixture_row_count"])
        checks["fixture_row_count"] = "pass" if ok else "fail"
        if not ok:
            errors.append(f"fixture_row_count {row_count} != {expect['fixture_row_count']}")
    cols = [c["name"] for c in schema]
    if "fixture_columns" in expect:
        want = [str(x) for x in expect["fixture_columns"]]
        ok = cols == want
        checks["fixture_columns"] = "pass" if ok else "fail"
        if not ok:
            errors.append(f"fixture_columns {cols} != {want}")

    return CaseResult(
        id=cid,
        passed=not errors,
        checks=checks or {"fixture": "pass"},
        observed={"table": table, "schema": schema, "row_count": row_count, "columns": cols},
        errors=errors,
    )


# ── Pipeline executor ───────────────────────────────────────────────────


def _run_pipeline(case: dict[str, Any], defaults: dict[str, Any]) -> CaseResult:
    from agent.runtime import run_analysis
    from agent.state import AnalysisContext

    cid = str(case["id"])
    expect = case.get("expect") or {}
    errors: list[str] = []
    checks: dict[str, str] = {}

    if case.get("require_llm") and not (os.environ.get("LLM_API_KEY") or "").strip():
        return CaseResult(
            id=cid,
            passed=True,
            skipped=True,
            skip_reason="LLM_API_KEY unset",
            checks={"skip": "pass"},
        )

    workspace_id = uuid4()
    dataset_id = uuid4()
    fixture = str(case.get("fixture") or defaults.get("fixture") or "fixtures/file/sales_mini.csv")
    table, schema, _rc = _prepare_file_fixture(fixture_rel=fixture, workspace_id=workspace_id)
    default_limit = int(case.get("default_limit") or defaults.get("default_limit") or 200)
    max_retries = int(case.get("max_retries") or defaults.get("max_retries") or 2)

    from app.services.duckdb_service import run_select

    def execute_select(sql: str, limit: int):
        return run_select(
            workspace_id=workspace_id,
            sql=sql,
            allowed_tables={table},
            default_limit=limit,
        )

    ctx = AnalysisContext(
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        question=str(case.get("question") or ""),
        duckdb_table=table,
        schema=schema,
        default_limit=default_limit,
        max_retries=max_retries,
        execute_select=execute_select,
        skill_id=str(case.get("skill_id") or defaults.get("skill_id") or "data.bi"),
        llm_api_key=(os.environ.get("LLM_API_KEY") or "").strip(),
        llm_base_url=(os.environ.get("LLM_BASE_URL") or "").strip(),
        llm_model=(os.environ.get("LLM_MODEL") or "").strip(),
        allow_heuristic_sql=False,  # forced for Eval
        allowed_tables=[table],
        source_type="file",
    )

    t0 = time.perf_counter()
    outcome = run_analysis(ctx)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    result_json = outcome.result_json or {}
    heuristic_used = _detect_heuristic(outcome.steps, result_json)
    sql_final = result_json.get("sql")
    preview = result_json.get("table_preview") or {}
    platform = result_json.get("platform") or {}
    run_meta = platform.get("run") if isinstance(platform, dict) else {}
    failure_class = None
    if isinstance(run_meta, dict):
        failure_class = run_meta.get("failure_class")
    if failure_class is None:
        failure_class = _map_failure_class(
            gate_ok=None,
            success=outcome.success,
            error_message=outcome.error_message,
            result_json=result_json,
            executed=bool(preview.get("rows") is not None),
        )

    # Infer gate from policy / steps
    gate_ok = None
    for step in outcome.steps or []:
        name = getattr(step, "node_name", "") or ""
        if name in {"validate_sql", "sql.validate_policy"}:
            gate_ok = getattr(step, "status", "") == "ok"
    if gate_ok is None and sql_final and outcome.success:
        gate_ok = True

    if expect.get("heuristic_forbidden"):
        checks["heuristic"] = "pass" if not heuristic_used else "fail"
        if heuristic_used:
            errors.append("heuristic SQL used but forbidden in Eval")

    if "success" in expect:
        ok = bool(outcome.success) == bool(expect["success"])
        checks["success"] = "pass" if ok else "fail"
        if not ok:
            errors.append(f"success expected {expect['success']}, got {outcome.success}")

    if expect.get("skill_id"):
        got_skill = None
        if isinstance(platform, dict):
            got_skill = platform.get("skill_id")
        ok_sk = got_skill == expect["skill_id"]
        checks["skill_id"] = "pass" if ok_sk else "fail"
        if not ok_sk:
            errors.append(f"skill_id expected {expect['skill_id']!r}, got {got_skill!r}")

    expect_gate = str(expect.get("gate") or "").lower()
    if expect_gate == "allow":
        checks["gate"] = "pass" if gate_ok else "fail"
        if not gate_ok:
            errors.append("expected gate allow")
    elif expect_gate == "deny":
        checks["gate"] = "pass" if gate_ok is False else "fail"
        if gate_ok is not False:
            errors.append("expected gate deny")

    sql_check = _score_sql_constraints(sql_final, expect.get("sql_constraints"), table=table)
    if expect.get("sql_constraints"):
        checks["sql_constraints"] = "pass" if sql_check.ok else "fail"
        if not sql_check.ok:
            errors.append(sql_check.detail)

    if outcome.success and expect.get("row_checks"):
        row_check = _score_row_checks(
            {
                "columns": preview.get("columns") or [],
                "rows": preview.get("rows") or [],
                "row_count": len(preview.get("rows") or []),
            },
            expect.get("row_checks"),
        )
        checks["result"] = "pass" if row_check.ok else "fail"
        if not row_check.ok:
            errors.append(row_check.detail)
        checks["execute"] = "pass"
    elif expect.get("row_checks") and not outcome.success:
        # expected failure cases may omit result
        if expect.get("success") is False:
            checks["result"] = "skip"
            checks["execute"] = "skip"
        else:
            checks["result"] = "fail"
            errors.append("expected row_checks but run failed")

    if outcome.success and expect.get("result_checks"):
        rc = _score_result_checks(
            {
                "columns": preview.get("columns") or [],
                "rows": preview.get("rows") or [],
                "row_count": len(preview.get("rows") or []),
            },
            expect.get("result_checks"),
        )
        checks["result_checks"] = "pass" if rc.ok else "fail"
        if not rc.ok:
            errors.append(rc.detail)
    elif expect.get("result_checks") and not outcome.success:
        if expect.get("success") is False:
            checks["result_checks"] = "skip"
        else:
            checks["result_checks"] = "fail"
            errors.append("expected result_checks but run failed")

    if "failure_class" in expect:
        want_fc = expect["failure_class"]
        if want_fc is None or want_fc == "none":
            ok_fc = failure_class is None
        else:
            ok_fc = failure_class == want_fc
        checks["failure_class"] = "pass" if ok_fc else "fail"
        if not ok_fc:
            errors.append(f"failure_class expected {want_fc!r}, got {failure_class!r}")

    link_obs = _extract_link_from_steps(outcome.steps)
    platform_sq = platform.get("sql_quality") if isinstance(platform, dict) else None
    if isinstance(platform_sq, dict) and platform_sq.get("link_status"):
        # Prefer platform projection when present (Trace/Eval consistency)
        link_obs = {
            "link_status": platform_sq.get("link_status"),
            "link_method": platform_sq.get("link_method"),
            "link_reason": platform_sq.get("link_reason"),
            "selected_tables": list(platform_sq.get("selected_tables") or []),
            "selected_columns": list(platform_sq.get("selected_columns") or []),
            "column_count_full": platform_sq.get("column_count_full"),
            "column_count_linked": platform_sq.get("column_count_linked"),
        }
    link_checks, link_errors = _score_link_expects(
        link_status=link_obs.get("link_status"),
        link_method=link_obs.get("link_method"),
        selected_columns=list(link_obs.get("selected_columns") or []),
        selected_tables=list(link_obs.get("selected_tables") or []),
        expect=expect,
        table=table,
    )
    checks.update(link_checks)
    errors.extend(link_errors)

    # Heuristic must never appear in scored eval
    if heuristic_used:
        checks["heuristic"] = "fail"
        if "heuristic SQL used" not in ";".join(errors):
            errors.append("heuristic SQL used in Eval")

    repair_data = _extract_repair_from_steps(outcome.steps)
    passed = not errors and all(v != "fail" for v in checks.values())
    return CaseResult(
        id=cid,
        passed=passed,
        checks=checks,
        observed={
            "success": outcome.success,
            "sql_final": sql_final,
            "gate_ok": gate_ok,
            "failure_class": failure_class,
            "row_count": len(preview.get("rows") or []),
            "retry_count": repair_data["retry_count"],
            "repair_history": repair_data["repair_history"],
            "repair_class": repair_data["repair_class"],
            "sql_source": "heuristic" if heuristic_used else ("llm" if ctx.llm_api_key else "none"),
            "heuristic_used": heuristic_used,
            "error_message": outcome.error_message,
            "latency_ms": latency_ms,
            "table": table,
            **link_obs,
        },
        errors=errors,
    )


# ── Repair Mock executor ────────────────────────────────────────────────


def _run_repair_mock(case: dict[str, Any], defaults: dict[str, Any]) -> CaseResult:
    """Deterministic mock repair flow: Gate reject → simulated retry → Gate pass.

    Simulates the complete repair cycle without LLM, using bad_sql / good_sql
    from the case definition.  Verifies repair_history, retry_count, and final
    gate_passed state.
    """
    from agent.kernel.policies import apply_sql_select_gate
    from agent.repair_classify import classify_repair_error, classify_with_hint

    cid = str(case["id"])
    expect = case.get("expect") or {}
    errors: list[str] = []
    checks: dict[str, str] = {}

    workspace_id = uuid4()
    fixture = str(case.get("fixture") or defaults.get("fixture") or "fixtures/file/sales_mini.csv")
    table, schema, _rc = _prepare_file_fixture(fixture_rel=fixture, workspace_id=workspace_id)
    allowed = {table}
    default_limit = int(case.get("default_limit") or defaults.get("default_limit") or 200)

    # ── Step 1: Inject bad SQL → Gate should reject ──────────────────────
    bad_sql = _subst(str(case.get("bad_sql") or ""), table=table)
    gate1, decision1 = apply_sql_select_gate(
        bad_sql, allowed_tables=allowed, default_limit=default_limit,
    )

    repair_class_bad = classify_repair_error(gate1.error, stage="validate") if not gate1.ok else None
    hint1 = classify_with_hint(gate1.error, stage="validate") if not gate1.ok else None

    # ── Step 2: Simulate retry → inject good SQL → Gate should pass ──────
    good_sql = _subst(str(case.get("good_sql") or ""), table=table)
    gate2, decision2 = apply_sql_select_gate(
        good_sql, allowed_tables=allowed, default_limit=default_limit,
    )

    repair_class_good = classify_repair_error(gate2.error, stage="validate") if not gate2.ok else None

    # ── Build mock repair_history ────────────────────────────────────────
    repair_history: list[dict[str, Any]] = []
    retry_count = 0

    if not gate1.ok:
        assert hint1 is not None
        repair_history.append({
            "attempt": 1,
            "sql_draft": bad_sql,
            "error": gate1.error,
            "repair_class": repair_class_bad,
            "is_repairable": hint1.is_repairable,
            "gate_passed": False,
            "stage": "validate_fail",
        })
        retry_count = 1

    if gate2.ok:
        repair_history.append({
            "attempt": retry_count,
            "sql_draft": good_sql,
            "sql_final": gate2.sql,
            "gate_passed": True,
            "stage": "validate_ok",
        })
    elif not gate2.ok and gate2.error:
        assert hint1 is not None  # for type checker; hint1 exists when gate1 failed
        # Second failure (non-repairable or persistent error)
        repair_history.append({
            "attempt": retry_count + 1,
            "sql_draft": good_sql,
            "error": gate2.error,
            "repair_class": repair_class_good,
            "is_repairable": classify_with_hint(gate2.error, stage="validate").is_repairable,
            "gate_passed": False,
            "stage": "validate_fail",
        })
        retry_count += 1

    success = bool(gate2.ok)
    final_sql = gate2.sql if gate2.ok else None

    # ── Verify expectations ──────────────────────────────────────────────
    repair_expect = expect.get("repair") or {}

    if "retry_count" in repair_expect:
        ok_rc = retry_count == int(repair_expect["retry_count"])
        checks["repair_retry_count"] = "pass" if ok_rc else "fail"
        if not ok_rc:
            errors.append(
                f"repair.retry_count expected {repair_expect['retry_count']}, got {retry_count}"
            )

    if "history_entries" in repair_expect:
        ok_he = len(repair_history) == int(repair_expect["history_entries"])
        checks["repair_history_entries"] = "pass" if ok_he else "fail"
        if not ok_he:
            errors.append(
                f"repair.history_entries expected {repair_expect['history_entries']}, "
                f"got {len(repair_history)}"
            )

    if "last_gate_passed" in repair_expect:
        want = bool(repair_expect["last_gate_passed"])
        got = repair_history[-1]["gate_passed"] if repair_history else False
        ok_lgp = got == want
        checks["repair_last_gate_passed"] = "pass" if ok_lgp else "fail"
        if not ok_lgp:
            errors.append(f"repair.last_gate_passed expected {want}, got {got}")

    if "first_repair_class" in repair_expect:
        want = str(repair_expect["first_repair_class"])
        got = repair_history[0].get("repair_class") if repair_history else None
        ok_frc = got == want
        checks["repair_first_repair_class"] = "pass" if ok_frc else "fail"
        if not ok_frc:
            errors.append(f"repair.first_repair_class expected {want!r}, got {got!r}")

    if "success" in expect:
        ok_s = success == bool(expect["success"])
        checks["success"] = "pass" if ok_s else "fail"
        if not ok_s:
            errors.append(f"success expected {expect['success']}, got {success}")

    if "failure_class" in expect:
        want_fc = expect["failure_class"]
        fc = None if success else (repair_class_bad or repair_class_good)
        if want_fc is None or want_fc == "none":
            ok_fc = fc is None
        else:
            ok_fc = fc == want_fc
        checks["failure_class"] = "pass" if ok_fc else "fail"
        if not ok_fc:
            errors.append(f"failure_class expected {want_fc!r}, got {fc!r}")

    passed = not errors and all(v != "fail" for v in checks.values())
    return CaseResult(
        id=cid,
        passed=passed,
        checks=checks,
        observed={
            "success": success,
            "sql_final": final_sql,
            "sql_raw": bad_sql,
            "gate_ok": gate2.ok,
            "gate_reason": gate2.error if not gate2.ok else None,
            "policy_id": decision2.policy_id,
            "failure_class": repair_class_bad if not success else None,
            "repair_class": repair_class_bad,
            "repair_history": repair_history,
            "retry_count": retry_count,
            "executed": False,
            "plane": "file",
            "table": table,
            "sql_source": "repair_mock",
            "heuristic_used": False,
            "tags": case.get("tags") or [],
        },
        errors=errors,
    )


# ── Case router ─────────────────────────────────────────────────────────


def run_case(case: dict[str, Any], defaults: dict[str, Any]) -> CaseResult:
    mode = str(case.get("mode") or defaults.get("mode") or "pipeline")
    if mode == "sql_inject":
        return _run_sql_inject(case, defaults)
    if mode == "fixture_meta":
        return _run_fixture_meta(case, defaults)
    if mode == "link_only":
        return _run_link_only(case, defaults)
    if mode == "pipeline":
        return _run_pipeline(case, defaults)
    if mode == "repair_mock":
        return _run_repair_mock(case, defaults)
    return CaseResult(id=str(case.get("id")), passed=False, errors=[f"unknown mode {mode!r}"])