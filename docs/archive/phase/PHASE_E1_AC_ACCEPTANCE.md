# E1-AC Acceptance — Schema Linking Lite + Eval Quality

**Status:** ✅ **FROZEN** (human-confirmed 2026-07-22) — see [PHASE_E1_AC_FINAL_STATUS.md](PHASE_E1_AC_FINAL_STATUS.md)  
**Scope:** A + C only · **B SQL Repair deferred (evidence-gated)**  
**Checklist:** [PHASE_E1_AC_LINK_EVAL_CHECKLIST.md](PHASE_E1_AC_LINK_EVAL_CHECKLIST.md)

---

## Constraints honored

| Constraint | Result |
|------------|--------|
| Kernel / Worker / Policy / Data Plane boundaries unchanged | Pass — Skill graph + Facade projection only |
| Existing `failure_class` semantics unchanged | Pass |
| No new Agent autonomy / Repair | Pass |
| Linking failures observable + classified (no silent fallback) | Pass — `fallback_full` / `failed` explicit |
| Eval `allow_heuristic_sql=false` | Pass |
| `quality` suite in release gate | Pass |

---

## Changed files

| Path | Change |
|------|--------|
| `agent/schema_linking.py` | **NEW** — deterministic linker + `LinkResult` |
| `agent/state.py` | Link state fields + `schema_link_max_columns` |
| `agent/graph.py` | `load_context → link_schema → generate_sql` (+ fail-closed) |
| `agent/nodes/pipeline.py` | `link_schema` node, prompt uses linked columns |
| `agent/prompts_sql.py` | Optional `link_status` note when not `ok` |
| `agent/runtime.py` | Project `platform.sql_quality` from steps |
| `agent/skills/data_bi/skill.py` | Pass `schema_link_max_columns` hint |
| `backend/app/services/task_service.py` | Trace API surfaces `sql_quality` |
| `evals/runner.py` | `link_only` mode + link expects + summary metrics |
| `evals/suites/quality/cases.yaml` | **NEW** quality suite |
| `evals/baselines/quality_latest.json` | **NEW** baseline |
| `backend/scripts/smoke_schema_linking.py` | **NEW** |
| `backend/scripts/smoke_eval_golden.py` | `--suite quality` |
| `backend/scripts/smoke_release_gate.py` | Wire linking smoke + quality eval |
| `docs/PHASE_E1_AC_*` | Design + acceptance |

---

## Smoke results

```text
smoke_schema_linking.py → SCHEMA_LINKING_OK
  S1 ok · S2 fallback_full · S3 failed · S4 identity · S5 partial
  S6 step + fail-closed · S7 platform.sql_quality

smoke_eval_golden --suite quality → EVAL_OK (6/6)
smoke_eval_golden --suite core --fail-on-regression → EVAL_OK (8/8, 2 skip)
```

---

## Eval quality metrics (baseline)

| Metric | Value (first baseline) |
|--------|-------------------------|
| `schema_link_cases` / `schema_link_passed` | 6 / 6 |
| `link_status_distribution` | ok:3, partial:1, fallback_full:1, failed:1 |
| `link_ok_rate` | 0.5 |
| `link_fallback_rate` | 0.1667 |
| `link_failed_rate` | 0.1667 |
| `heuristic_use_count` | 0 |

**Before A+C:** no `link_*` fields in Eval reports (schema dump opaque).  
**After:** Trace step + `platform.sql_quality` + quality suite rates are comparable for before/after linking changes. Fallback is counted, not hidden.

---

## Release gate impact

| Addition | Blocking? |
|----------|-----------|
| `smoke_schema_linking.py` | **Yes** |
| `smoke_eval_golden --suite quality` (+ baseline if present) | **Yes** |
| Existing core eval / other smokes | Unchanged; core still green |

Gate now runs **longer by ~1 quality suite + linking smoke**; no change to Kernel/Worker/Policy smokes themselves.

---

## Explicitly deferred / freeze

- Slice **B** SQL Repair — **evidence-gated**; do not start without Eval proof ([FINAL_STATUS](PHASE_E1_AC_FINAL_STATUS.md))  
- Frontend Trace polish (E2) — next **design** candidate, not in this freeze  
- Softening Gate rules  

**Next candidates (no coding):** [PHASE_NEXT_CANDIDATES.md](PHASE_NEXT_CANDIDATES.md)
