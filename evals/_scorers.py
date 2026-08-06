"""Eval scoring functions — SQL constraints, result checks, row checks, link expects."""

from __future__ import annotations

from typing import Any

from evals._models import CheckResult


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


def _score_result_checks(
    preview: dict[str, Any] | None,
    checks: dict[str, Any] | None,
) -> CheckResult:
    """Validate exact result correctness: columns, row count, and row values."""
    if not checks:
        return CheckResult("result_checks", True, "none")
    if not preview:
        return CheckResult("result_checks", False, "missing preview")
    rows = preview.get("rows") or []
    cols = [str(c) for c in (preview.get("columns") or [])]
    n = int(preview.get("row_count") if preview.get("row_count") is not None else len(rows))
    errors: list[str] = []

    expected_cols = checks.get("expected_columns")
    if expected_cols is not None:
        got_lower = [c.lower() for c in cols]
        exp_lower = [str(c).lower() for c in expected_cols]
        if got_lower != exp_lower:
            errors.append(f"expected_columns: got {cols}, expected {expected_cols}")

    if "row_count_exact" in checks:
        if n != int(checks["row_count_exact"]):
            errors.append(f"row_count_exact: got {n}, expected {checks['row_count_exact']}")

    expected_rows = checks.get("expected_rows")
    if expected_rows is not None:
        if len(expected_rows) != n:
            errors.append(f"expected_rows count: got {n}, expected {len(expected_rows)}")
        else:
            for i, exp_row in enumerate(expected_rows):
                if not isinstance(exp_row, dict):
                    continue
                actual_row = rows[i] if i < len(rows) else None
                if not isinstance(actual_row, dict):
                    errors.append(f"row[{i}]: expected dict, got {type(actual_row).__name__}")
                    continue
                for key, exp_val in exp_row.items():
                    actual_val = actual_row.get(key)
                    if actual_val is None:
                        for k, v in actual_row.items():
                            if str(k).lower() == str(key).lower():
                                actual_val = v
                                break
                    if str(actual_val) != str(exp_val):
                        errors.append(
                            f"row[{i}].{key}: got {actual_val!r}, expected {exp_val!r}"
                        )

    if errors:
        return CheckResult("result_checks", False, "; ".join(errors))
    return CheckResult("result_checks", True, "ok")


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