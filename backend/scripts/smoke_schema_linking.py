"""Smoke E1-A: Schema Linking Lite (deterministic, Skill-local).

Covers link_status taxonomy: ok / partial / fallback_full / failed / identity.
No Kernel / Worker / Policy / Plane changes. No silent fallback.

Usage (from backend/):
  python scripts/smoke_schema_linking.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.core.repo_path import ensure_repo_root_on_path  # noqa: E402

ensure_repo_root_on_path()

from agent.nodes import pipeline as nodes  # noqa: E402
from agent.runtime import run_analysis  # noqa: E402
from agent.schema_linking import link_schema  # noqa: E402
from agent.state import AnalysisContext, StepRecord  # noqa: E402


WIDE = [
    {"name": "region", "type": "VARCHAR"},
    {"name": "product", "type": "VARCHAR"},
    {"name": "amount", "type": "DOUBLE"},
    {"name": "noise_a", "type": "VARCHAR"},
    {"name": "noise_b", "type": "INTEGER"},
    {"name": "noise_c", "type": "VARCHAR"},
    {"name": "noise_d", "type": "DOUBLE"},
    {"name": "noise_e", "type": "VARCHAR"},
    {"name": "noise_f", "type": "INTEGER"},
    {"name": "noise_g", "type": "VARCHAR"},
    {"name": "noise_h", "type": "DOUBLE"},
    {"name": "noise_i", "type": "VARCHAR"},
    {"name": "noise_j", "type": "INTEGER"},
]


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> None:
    # S1: ok — overlap selects region/amount, excludes noise under K
    r1 = link_schema(
        question="sum amount by region",
        schema=WIDE,
        table="sales_wide",
        allowed_tables=["sales_wide"],
        max_columns=4,
    )
    _assert(r1.link_status == "ok", f"S1 status={r1.link_status}")
    _assert(r1.link_method == "token_overlap", f"S1 method={r1.link_method}")
    _assert("region" in r1.selected_columns and "amount" in r1.selected_columns, f"S1 cols={r1.selected_columns}")
    _assert("noise_a" not in r1.selected_columns, f"S1 should exclude noise: {r1.selected_columns}")
    print("S1 ok: PASS")

    # S2: fallback_full — no overlap, explicit recovery (not silent)
    r2 = link_schema(
        question="what is the weather tomorrow in the city",
        schema=WIDE,
        table="sales_wide",
        max_columns=4,
    )
    _assert(r2.link_status == "fallback_full", f"S2 status={r2.link_status}")
    _assert(r2.link_method == "fallback_full", f"S2 method={r2.link_method}")
    _assert(r2.link_reason == "no_token_overlap", f"S2 reason={r2.link_reason}")
    _assert(len(r2.selected_columns) == 4, f"S2 capped cols={r2.selected_columns}")
    print("S2 fallback_full: PASS")

    # S3: failed — empty schema
    r3 = link_schema(question="sum amount", schema=[], table="t")
    _assert(r3.link_status == "failed", f"S3 status={r3.link_status}")
    _assert(r3.link_reason == "schema_empty", f"S3 reason={r3.link_reason}")
    _assert(r3.selected_columns == [], f"S3 cols={r3.selected_columns}")
    print("S3 failed: PASS")

    # S4: identity — schema ≤ K
    small = WIDE[:3]
    r4 = link_schema(question="anything", schema=small, table="sales", max_columns=12)
    _assert(r4.link_status == "ok", f"S4 status={r4.link_status}")
    _assert(r4.link_method == "identity", f"S4 method={r4.link_method}")
    _assert(r4.selected_columns == ["region", "product", "amount"], f"S4 cols={r4.selected_columns}")
    print("S4 identity: PASS")

    # S5: partial — single weak hit
    r5 = link_schema(question="filter by region", schema=WIDE, table="sales_wide", max_columns=4)
    _assert(r5.link_status == "partial", f"S5 status={r5.link_status}")
    _assert("region" in r5.selected_columns, f"S5 cols={r5.selected_columns}")
    print("S5 partial: PASS")

    # S6: pipeline node emits step; failed routes closed
    steps: list[StepRecord] = []

    def sink(step: StepRecord) -> None:
        steps.append(step)

    ctx = AnalysisContext(
        workspace_id=uuid4(),
        dataset_id=uuid4(),
        question="sum amount by region",
        duckdb_table="sales_wide",
        schema=WIDE,
        default_limit=200,
        max_retries=0,
        execute_select=lambda _sql, _lim: {"columns": [], "rows": [], "row_count": 0},
        allow_heuristic_sql=False,
        allowed_tables=["sales_wide"],
        schema_link_max_columns=4,
    )
    state = nodes.load_context({}, ctx=ctx, sink=sink)
    state = nodes.link_schema(state, ctx=ctx, sink=sink)
    link_steps = [s for s in steps if s.node_name == "link_schema"]
    _assert(len(link_steps) == 1, "S6 missing link_schema step")
    _assert(link_steps[0].status == "ok", f"S6 step status={link_steps[0].status}")
    _assert((link_steps[0].output_json or {}).get("link_status") == "ok", "S6 output link_status")
    _assert(nodes.route_after_link(state) == "generate_sql", "S6 route")

    fail_ctx = AnalysisContext(
        workspace_id=uuid4(),
        dataset_id=uuid4(),
        question="x",
        duckdb_table="t",
        schema=[],
        default_limit=200,
        max_retries=0,
        execute_select=lambda _sql, _lim: {"columns": [], "rows": [], "row_count": 0},
        allow_heuristic_sql=False,
    )
    fail_steps: list[StepRecord] = []
    fail_state = nodes.link_schema(
        {"question": "x", "duckdb_table": "t", "schema": []},
        ctx=fail_ctx,
        sink=fail_steps.append,
    )
    _assert(fail_state.get("link_status") == "failed", "S6b failed status")
    _assert(nodes.route_after_link(fail_state) == "fail", "S6b must fail closed")
    _assert(fail_steps[0].status == "error", "S6b step error")
    print("S6 pipeline step + fail-closed: PASS")

    # S8: synonym v2 — Chinese jargon maps to region/amount
    r8 = link_schema(
        question="按区域汇总销售额",
        schema=WIDE,
        table="sales_wide",
        max_columns=4,
    )
    _assert(r8.link_status == "ok", f"S8 status={r8.link_status}")
    _assert(r8.link_method == "synonym_overlap", f"S8 method={r8.link_method}")
    _assert("region" in r8.selected_columns and "amount" in r8.selected_columns, f"S8 cols={r8.selected_columns}")
    _assert(r8.synonyms_applied, f"S8 synonyms_applied={r8.synonyms_applied}")
    print("S8 synonym_zh: PASS")

    # S7: Facade projects platform.sql_quality (even on honesty fail)
    outcome = run_analysis(
        AnalysisContext(
            workspace_id=uuid4(),
            dataset_id=uuid4(),
            question="各地区销售额合计是多少？",
            duckdb_table="sales_mini",
            schema=small,
            default_limit=200,
            max_retries=0,
            execute_select=lambda _sql, _lim: {"columns": [], "rows": [], "row_count": 0},
            allow_heuristic_sql=False,
            allowed_tables=["sales_mini"],
        )
    )
    sq = (outcome.result_json.get("platform") or {}).get("sql_quality")
    _assert(isinstance(sq, dict), f"S7 missing sql_quality: {outcome.result_json.get('platform')}")
    _assert(sq.get("link_status") in {"ok", "partial", "fallback_full", "failed"}, f"S7 status={sq}")
    _assert(any(s.node_name == "link_schema" for s in outcome.steps), "S7 no link_schema step")
    print("S7 platform.sql_quality: PASS")

    print("SCHEMA_LINKING_OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"SCHEMA_LINKING_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
