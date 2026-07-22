"""P0-1 Eval runner library — Facade / Gate / Plane only (no Kernel edits)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

RUNNER_VERSION = 1
EVALS_ROOT = Path(__file__).resolve().parent


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class CaseResult:
    id: str
    passed: bool
    skipped: bool = False
    skip_reason: str | None = None
    checks: dict[str, str] = field(default_factory=dict)
    observed: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "passed": self.passed,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "checks": self.checks,
            "observed": self.observed,
            "errors": self.errors,
        }


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


def _subst(text: str, *, table: str) -> str:
    return text.replace("{{table}}", table)


def _ci_contains(hay: str, needle: str) -> bool:
    return needle.lower() in hay.lower()


def _detect_heuristic(steps: list[Any], result_json: dict[str, Any] | None) -> bool:
    for step in steps or []:
        out = getattr(step, "output_json", None) or {}
        if not isinstance(out, dict):
            continue
        llm = out.get("llm")
        if isinstance(llm, dict) and llm.get("mode") == "heuristic":
            return True
        if out.get("sql_source") == "heuristic":
            return True
    platform = (result_json or {}).get("platform") or {}
    if isinstance(platform, dict) and platform.get("sql_source") == "heuristic":
        return True
    return False


def _map_failure_class(
    *,
    gate_ok: bool | None,
    success: bool | None,
    error_message: str | None,
    result_json: dict[str, Any] | None,
    executed: bool,
) -> str | None:
    platform = (result_json or {}).get("platform") or {}
    run = platform.get("run") if isinstance(platform, dict) else None
    if isinstance(run, dict) and run.get("failure_class"):
        return str(run["failure_class"])
    if gate_ok is False:
        return "policy_denied"
    if not success:
        msg = (error_message or "").lower()
        if "connector" in msg or "connection" in msg:
            return "connector_error"
        if "gate" in msg or "allowlist" in msg or "forbidden" in msg:
            return "policy_denied"
        return "skill_error"
    return None


def _score_sql_constraints(
    sql: str | None,
    constraints: dict[str, Any] | None,
    *,
    table: str,
) -> CheckResult:
    if not constraints:
        return CheckResult("sql_constraints", True, "none")
    if not sql:
        return CheckResult("sql_constraints", False, "missing sql")
    errors: list[str] = []
    for t in constraints.get("must_include_tables") or []:
        want = _subst(str(t), table=table)
        if want.lower() not in sql.lower():
            errors.append(f"missing table {want!r}")
    any_needles = constraints.get("must_match_any") or []
    if any_needles and not any(_ci_contains(sql, str(n)) for n in any_needles):
        errors.append(f"none of must_match_any matched: {any_needles}")
    for n in constraints.get("must_not_match") or []:
        if _ci_contains(sql, str(n)):
            errors.append(f"forbidden match {n!r}")
    if errors:
        return CheckResult("sql_constraints", False, "; ".join(errors))
    return CheckResult("sql_constraints", True, "ok")


def _score_row_checks(preview: dict[str, Any] | None, checks: dict[str, Any] | None) -> CheckResult:
    if not checks:
        return CheckResult("row_checks", True, "none")
    if not preview:
        return CheckResult("row_checks", False, "missing preview")
    rows = preview.get("rows") or []
    cols = [str(c) for c in (preview.get("columns") or [])]
    n = int(preview.get("row_count") if preview.get("row_count") is not None else len(rows))
    errors: list[str] = []
    if "min_rows" in checks and n < int(checks["min_rows"]):
        errors.append(f"min_rows: got {n} < {checks['min_rows']}")
    if "max_rows" in checks and n > int(checks["max_rows"]):
        errors.append(f"max_rows: got {n} > {checks['max_rows']}")
    if "row_count_exact" in checks and n != int(checks["row_count_exact"]):
        errors.append(f"row_count_exact: got {n} != {checks['row_count_exact']}")
    for want in checks.get("columns_contain") or []:
        if not any(want.lower() == c.lower() or want.lower() in c.lower() for c in cols):
            errors.append(f"columns_contain missing {want!r} in {cols}")
    for spec in checks.get("values_contain") or []:
        if not isinstance(spec, dict):
            continue
        col = str(spec.get("column") or "")
        val = spec.get("value")
        found = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            # case-insensitive column match
            actual = None
            for k, v in row.items():
                if str(k).lower() == col.lower():
                    actual = v
                    break
            if actual is None:
                continue
            if str(actual) == str(val):
                found = True
                break
        if not found:
            errors.append(f"values_contain not found {col}={val!r}")
    if errors:
        return CheckResult("row_checks", False, "; ".join(errors))
    return CheckResult("row_checks", True, "ok")


def _prepare_file_fixture(
    *,
    fixture_rel: str,
    workspace_id,
) -> tuple[str, list[dict[str, str]], int]:
    from app.core.storage_paths import ensure_storage_dirs
    from app.services import duckdb_service

    ensure_storage_dirs()
    csv_path = (EVALS_ROOT / fixture_rel).resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(f"Fixture missing: {csv_path}")
    table = f"ds_eval_{uuid4().hex[:12]}"
    imported = duckdb_service.import_file(
        workspace_id=workspace_id,
        table_name=table,
        file_path=csv_path,
    )
    schema = list(imported["schema"])
    row_count = int(imported["row_count"])
    return table, schema, row_count


def _execute_file(*, workspace_id, sql: str, table: str, default_limit: int) -> dict[str, Any]:
    from app.services import duckdb_service

    return duckdb_service.run_select(
        workspace_id=workspace_id,
        sql=sql,
        allowed_tables={table},
        default_limit=default_limit,
    )


def _execute_postgres(*, sql: str, allowed_tables: set[str], default_limit: int) -> dict[str, Any]:
    from app.services import postgres_ro_service

    return postgres_ro_service.run_select(
        sql=sql,
        allowed_tables=allowed_tables,
        default_limit=default_limit,
    )


def _run_sql_inject(case: dict[str, Any], defaults: dict[str, Any]) -> CaseResult:
    from agent.kernel.policies import apply_sql_select_gate

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
            "row_count": (preview or {}).get("row_count"),
            "executed": executed,
            "plane": plane,
            "table": table,
            "sql_source": "injected",
            "heuristic_used": False,
        },
        errors=errors,
    )


def _score_link_expects(
    *,
    link_status: str | None,
    link_method: str | None,
    selected_columns: list[str],
    selected_tables: list[str],
    expect: dict[str, Any],
    table: str = "",
) -> tuple[dict[str, str], list[str]]:
    """Score Schema Linking expects; returns (checks, errors)."""
    checks: dict[str, str] = {}
    errors: list[str] = []
    cols_l = [c.lower() for c in selected_columns]
    tables_l = [t.lower() for t in selected_tables]

    if "link_status" in expect:
        want = str(expect["link_status"])
        ok = link_status == want
        checks["link_status"] = "pass" if ok else "fail"
        if not ok:
            errors.append(f"link_status expected {want!r}, got {link_status!r}")

    if "link_status_in" in expect:
        allowed = {str(x) for x in (expect["link_status_in"] or [])}
        ok = link_status in allowed
        checks["link_status_in"] = "pass" if ok else "fail"
        if not ok:
            errors.append(f"link_status {link_status!r} not in {sorted(allowed)}")

    if "link_method" in expect:
        want = str(expect["link_method"])
        ok = link_method == want
        checks["link_method"] = "pass" if ok else "fail"
        if not ok:
            errors.append(f"link_method expected {want!r}, got {link_method!r}")

    if "link_method_in" in expect:
        allowed = {str(x) for x in (expect["link_method_in"] or [])}
        ok = link_method in allowed
        checks["link_method_in"] = "pass" if ok else "fail"
        if not ok:
            errors.append(f"link_method {link_method!r} not in {sorted(allowed)}")

    for want in expect.get("selected_columns_contain") or []:
        w = str(want).lower()
        ok = any(w == c or w in c for c in cols_l)
        key = f"selected_columns_contain:{want}"
        checks[key] = "pass" if ok else "fail"
        if not ok:
            errors.append(f"selected_columns missing {want!r} in {selected_columns}")

    for bad in expect.get("selected_columns_exclude") or []:
        b = str(bad).lower()
        hit = any(b == c or b in c for c in cols_l)
        key = f"selected_columns_exclude:{bad}"
        checks[key] = "pass" if not hit else "fail"
        if hit:
            errors.append(f"selected_columns unexpectedly contains {bad!r}")

    for want in expect.get("selected_tables_contain") or []:
        w = _subst(str(want), table=table or (selected_tables[0] if selected_tables else "")).lower()
        ok = any(w == t or w in t for t in tables_l)
        key = f"selected_tables_contain:{want}"
        checks[key] = "pass" if ok else "fail"
        if not ok:
            errors.append(f"selected_tables missing {want!r} in {selected_tables}")

    return checks, errors


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
            "retry_count": None,
            "sql_source": "heuristic" if heuristic_used else ("llm" if ctx.llm_api_key else "none"),
            "heuristic_used": heuristic_used,
            "error_message": outcome.error_message,
            "latency_ms": latency_ms,
            "table": table,
            **link_obs,
        },
        errors=errors,
    )


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
    return CaseResult(id=str(case.get("id")), passed=False, errors=[f"unknown mode {mode!r}"])


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
    }


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
