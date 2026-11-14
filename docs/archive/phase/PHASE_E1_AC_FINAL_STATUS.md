# E1-AC Final Status — Frozen

**Status:** ✅ **FROZEN** (human-confirmed 2026-07-22)  
**Scope frozen:** Schema Linking Lite (**A**) + Eval Quality (**C**)  
**Deferred indefinitely until Eval evidence:** SQL Repair (**B**)

---

## Final verdict

| Item | Verdict |
|------|---------|
| Schema Linking Lite in `data.bi` Skill graph | ✅ Done — `load_context → link_schema → generate_sql → …` |
| Trace / `platform.sql_quality` | ✅ Done — `link_status` / method / columns observable |
| Silent fallback forbidden | ✅ Enforced — `fallback_full` / `failed` explicit |
| Eval quality suite + baseline | ✅ Done — `evals/suites/quality` + `baselines/quality_latest.json` |
| Release gate | ✅ Wired — `smoke_schema_linking` + `smoke_eval_golden --suite quality` |
| Kernel / Worker / Policy / Data Plane boundaries | ✅ Untouched |
| `failure_class` semantics | ✅ Unchanged |
| Eval `allow_heuristic_sql=false` | ✅ Kept |
| SQL Repair | ⏸ **Not started** — evidence-gated |

**Acceptance:** [PHASE_E1_AC_ACCEPTANCE.md](PHASE_E1_AC_ACCEPTANCE.md)  
**Checklist (as-built):** [PHASE_E1_AC_LINK_EVAL_CHECKLIST.md](PHASE_E1_AC_LINK_EVAL_CHECKLIST.md)

---

## Freeze rules (do not reopen casually)

1. **Do not** implement SQL Repair / expand retry autonomy without Eval proof of classifiable repair yield.  
2. **Do not** change Kernel / Worker / Policy / Data Plane boundaries under the E1 banner.  
3. **Do not** alter existing `failure_class` vocabulary for linking cosmetic reasons.  
4. **Do not** relax Eval heuristic discipline (`allow_heuristic_sql=false`).  
5. Linking algorithm tweaks are allowed only if **quality suite + baseline regression** stay honest (no hiding `fallback_full`).

---

## Observation window (before next coding slice)

**Active log:** [OBSERVATION_LOG.md](../reviews/OBSERVATION_LOG.md)

Use existing Eval / Trace — **observe, do not build Repair yet**.

| # | Question | Signal source |
|---|----------|---------------|
| 1 | Does `link_ok_rate` stabilize / rise after Prompt or linker tweaks? | `evals` quality report `summary.link_ok_rate` |
| 2 | Is `fallback_full` mostly from real wide/ambiguous schemas (vs weak tokenizer)? | Case `link.fallback.*` + live Trace `link_reason=no_token_overlap` vs schema width |
| 3 | Do SQL failures concentrate in **linking**, **generation**, or **execution**? | Steps: `link_schema` error · `generate_sql` error · Gate/execute errors; `failure_class` + node_name |

**Repair open criterion (all required):**

- Measurable cluster of failures with a **closed** repair taxonomy (not free-form Agent retry).  
- Failures are **not** primarily linking misses (fix linking first).  
- Eval can score repair attempts without expanding Kernel / Policy.

---

## Baseline snapshot (freeze day)

| Metric | `quality_latest` |
|--------|------------------|
| Cases passed | 6/6 |
| `link_status_distribution` | ok:3 · partial:1 · fallback_full:1 · failed:1 |
| `link_ok_rate` | 0.5 |
| `link_fallback_rate` | 0.1667 |
| `link_failed_rate` | 0.1667 |
| `heuristic_use_count` | 0 |

---

## Next docs (design only)

- Roadmap: [ENHANCEMENT_ROADMAP.md](../roadmap/ENHANCEMENT_ROADMAP.md)  
- Next candidates (no coding): [PHASE_NEXT_CANDIDATES.md](PHASE_NEXT_CANDIDATES.md)
