# E1 — Text-to-SQL Quality Implementation Checklist

**Status:** E1 **A+C frozen** — [FINAL_STATUS](./PHASE_E1_AC_FINAL_STATUS.md). This doc remains full A/B/C design; **B evidence-gated / not started**.  
**Date:** 2026-07-22  
**Parent:** [ENHANCEMENT_ROADMAP.md](./ENHANCEMENT_ROADMAP.md) (Wave 1)  
**Architecture lock:**

```text
Skill (data.bi fixed LangGraph) → Policy (sql.select_gate) → Data Plane → Trace
```

**Rule:** Additive Skill/Eval changes only. **No** Kernel / Worker / Policy Gate algorithm / Data Plane boundary changes. **No** RAG / ReAct / Multi-Agent / Semantic Layer product.

---

## 0. Goals

| Goal | Meaning |
|------|---------|
| Higher SQL generation quality | Better column/table focus before LLM generate |
| Verifiability | Linking + repair decisions observable on Trace and Eval |
| Controlled repair | Structured failure classes; same `max_retries` ceiling; failure semantics unchanged |
| CI-safe Eval | Core suite stays deterministic; quality suite extends framework |

**Priority order (implement in this sequence):**

1. Schema Linking Lite  
2. SQL Repair (controlled)  
3. Eval Quality extension  

---

## 1. Slice A — Schema Linking Lite

### 1.1 Intent

Make **which table/columns** enter the Text-to-SQL prompt an explicit, logged step — not a silent full-schema dump.

### 1.2 Behavior

```text
load_context
  → link_schema          # NEW thin node (or equivalent pre-step)
  → generate_sql         # prompts use linked view
  → validate_sql → …
```

| Rule | Detail |
|------|--------|
| Input | Full `schema` + `question` + primary `duckdb_table` + `allowed_tables` |
| Output | `selected_tables`, `selected_columns` (ordered), `link_method`, optional `link_scores` |
| Algorithm (v1) | Deterministic heuristics only: name/token overlap with question; prefer metric/dim name patterns; always keep primary table; cap **top-K columns** (e.g. K=12, settings) |
| Fallback | If overlap empty → keep all columns (or first K) + `link_method=fallback_full` |
| Prompt | `build_text_to_sql_prompts` receives **linked** column list; still lists allowed tables for Gate honesty |
| Observability | Step `link_schema` + Trace/platform summary fields (see §3) |

**Not in v1:** embeddings, FK graph crawler, multi-hop join planner, business glossary product.

### 1.3 Implementation checklist (Slice A)

- [ ] Add `link_schema` node (preferred) **or** call linker at start of `generate_sql` with dedicated step emit  
- [ ] Pure function module e.g. `agent/schema_linking.py` (unit-testable, no LLM)  
- [ ] Wire graph: `load_context → link_schema → generate_sql`  
- [ ] Update `prompts_sql.build_text_to_sql_prompts` to accept linked columns (+ optional note of omitted count)  
- [ ] Emit step + state fields  
- [ ] Smoke: `smoke_schema_linking.py` (deterministic fixtures)  
- [ ] Doc: how K / fallback works  

---

## 2. Slice B — SQL Repair (controlled)

### 2.1 Intent

Replace opaque “paste gate_error and retry” with a **closed taxonomy** of repair hints, without infinite retry or changing terminal `failure_class` semantics.

### 2.2 Behavior

Keep existing edges:

```text
validate_sql ──(deny, retry≤max)──► generate_sql
execute_sql  ──(fail, retry≤max)──► generate_sql
```

On deny/fail **before** routing back to generate:

1. Classify error → `repair_class` (enum)  
2. Build short `repair_hint` (structured string for prompt)  
3. Increment `retry_count` as today  
4. If `retry_count > max_retries` → `fail` (unchanged)

| `repair_class` | When | Hint focus |
|----------------|------|------------|
| `gate_forbidden_keyword` | Gate: DDL/DML/admin | Generate SELECT only |
| `gate_multi_statement` | Gate: `;` / multi | Single SELECT |
| `gate_not_select` | Gate: not SELECT/WITH | SELECT only |
| `gate_table_not_allowed` | Gate: allowlist miss | Use only allowed/selected tables |
| `gate_empty_or_parse` | Empty / parse fail | Valid SELECT JSON |
| `execute_error` | Plane execute exception | Fix SQL vs schema/types; still SELECT |
| `none` | Success path | — |

**Rules:**

- Classification is **deterministic** (regex/substring on Gate messages + execute errors) — no LLM judge.  
- `max_retries` unchanged (settings / context).  
- Terminal failures still map via Worker/`failure_class` as today (`policy_denied` / `skill_error` / `connector_error`). Repair does **not** invent new Run failure classes.  
- Prompt gets `repair_class` + `repair_hint` **in addition to** raw error (raw may be truncated).

### 2.3 Implementation checklist (Slice B)

- [ ] Add `agent/repair_classify.py` (pure)  
- [ ] Call from `validate_sql` / `execute_sql` failure branches  
- [ ] State: `repair_class`, `repair_hint`, keep `gate_error`/`error`  
- [ ] Prompt: include structured repair block when present  
- [ ] Step output includes `repair_class` on validate/execute error emits  
- [ ] Smoke: classify fixtures → expected enum  
- [ ] Confirm retry still stops at `max_retries`  

---

## 3. Data structures / Trace changes

### 3.1 `AnalysisState` additions

```text
selected_tables: list[str]
selected_columns: list[str]          # column names (primary table focus)
link_method: str                     # token_overlap | fallback_full | …
repair_class: str                    # enum above or none
repair_hint: str
```

Existing: `schema`, `gate_error`, `retry_count`, `max_retries` — keep.

### 3.2 Step records

| node_name | Notable output_json |
|-----------|---------------------|
| `link_schema` | `selected_tables`, `selected_columns`, `link_method`, `column_count_full`, `column_count_linked` |
| `generate_sql` | existing + echo `selected_columns` / `repair_class` in input_json when set |
| `validate_sql` | on deny: `repair_class`, `repair_hint` |
| `execute_sql` | on fail: `repair_class`, `repair_hint` |

### 3.3 `platform` / Execution Trace (additive)

Prefer projecting into existing Trace without Kernel rewrite:

```json
"platform": {
  "sql_quality": {
    "selected_tables": ["…"],
    "selected_columns": ["…"],
    "link_method": "token_overlap",
    "repair_attempts": [
      { "retry": 1, "repair_class": "gate_table_not_allowed" }
    ],
    "final_repair_class": null
  }
}
```

**Rules:**

- Audit / explain only — **not** a permission or Gate cache.  
- Built in Skill Facade / pipeline result projection (same pattern as other platform fields).  
- Optional: also surface under `platform.execution.summary` counts (`repair_count`) if low-touch.

### 3.4 Eval report extensions

```json
"summary": {
  "…existing…",
  "schema_link_coverage": 0.0,
  "repair_class_distribution": { "gate_table_not_allowed": 1, "none": 10 },
  "quality_result_match_rate": null
}
```

- Core suite: may assert link step exists on pipeline cases; repair distribution on inject/pipeline failures.  
- Quality/llm suite: `result_match` remains primary accuracy metric.

---

## 4. Slice C — Eval Quality extension

### 4.1 Intent

Extend P0-1 Evaluation Framework so quality changes are **regressable**, without turning CI into a flaky live-LLM gate.

### 4.2 Suites

| Suite | CI? | Content |
|-------|-----|---------|
| `core` | **Yes** (keep) | Deterministic Gate/execute + fixture; add **link_schema unit cases** via `mode: link_only` or dedicated smoke; optional pipeline case asserts `selected_columns` non-empty when heuristic off fails |
| `quality` (new) | Optional in release gate **if fully deterministic**; else manual | Cases with `expect.selected_columns_contain` / `expect.link_method`; sql_inject unchanged |
| `llm` | **No** default CI | NL questions + `row_checks`; documents quality; run with key |

### 4.3 New expect fields (cases.yaml)

```yaml
expect:
  selected_columns_contain: ["region", "amount"]   # subset
  selected_columns_exclude: ["secret_col"]         # optional
  link_method_in: ["token_overlap", "fallback_full"]
  repair_class: gate_table_not_allowed             # for inject/pipeline fail paths
```

### 4.4 Implementation checklist (Slice C)

- [ ] Extend `evals/runner.py` scorers for new expects  
- [ ] Add `evals/suites/quality/cases.yaml` (small, deterministic)  
- [ ] Update baseline policy: core baseline unchanged unless intentional; quality baseline optional  
- [ ] `smoke_eval_golden.py --suite quality`  
- [ ] Release gate: run `quality` **only if** suite is deterministic (recommended: **yes, include quality** if no live LLM)  
- [ ] Document how to run `--suite llm` for accuracy  

---

## 5. Impact file range

### Expected to change / add

| Path | Slice | Change |
|------|-------|--------|
| `agent/schema_linking.py` | A | **NEW** linker |
| `agent/repair_classify.py` | B | **NEW** classifier |
| `agent/state.py` | A/B | State fields |
| `agent/graph.py` | A | Edge `load_context → link_schema → generate_sql` |
| `agent/nodes/pipeline.py` | A/B | New node; repair on validate/execute; prompt wiring |
| `agent/prompts_sql.py` | A/B | Linked schema + repair block |
| `agent/skills/data_bi/skill.py` or result projection | A/B | `platform.sql_quality` |
| `agent/kernel/execution_trace.py` | A/B | Optional summary fields only if needed |
| `evals/runner.py` | C | New expects + metrics |
| `evals/suites/quality/cases.yaml` | C | **NEW** |
| `evals/suites/core/cases.yaml` | C | Minimal additive asserts if safe |
| `evals/baselines/*` | C | Update only after intentional green |
| `backend/scripts/smoke_schema_linking.py` | A | **NEW** |
| `backend/scripts/smoke_repair_classify.py` | B | **NEW** (or combined) |
| `backend/scripts/smoke_eval_golden.py` | C | `--suite quality` |
| `backend/scripts/smoke_release_gate.py` | C | Wire quality if deterministic |
| `docs/PHASE_E1_*` | all | Checklist / acceptance |
| `docs/ENHANCEMENT_ROADMAP.md` | — | Status note |

### Explicitly out of touch

| Path | Why |
|------|-----|
| `agent/kernel/runtime.py` / registry contracts | Kernel freeze |
| `backend/app/workers/*` lifecycle | No boundary change (may pass through result_json only) |
| `agent/gates/sql_gate.py` | Gate rules unchanged; repair **consumes** messages |
| `duckdb_service` / `postgres_ro_service` | Plane unchanged |
| `permissions.py` / ACL | Orthogonal |
| `cost_budget.py` | Orthogonal |
| Frontend | **Out of E1** (E2 UX wave); Trace fields backend-first |

---

## 6. Acceptance criteria

### Schema Linking Lite

- [ ] Every `data.bi` pipeline run emits `link_schema` step (or equivalent) with `selected_columns`.  
- [ ] Prompt columns ⊆ full schema; primary table always selected.  
- [ ] Deterministic smoke on fixed question/schema → stable selected set.  
- [ ] `platform.sql_quality.selected_columns` present on successful/partial platform projection when pipeline runs.

### SQL Repair

- [ ] Closed `repair_class` enum only (listed in §2.2).  
- [ ] Retries still capped by `max_retries`; no new infinite loop.  
- [ ] Terminal `failure_class` vocabulary unchanged.  
- [ ] Prompt receives structured hint; smoke covers ≥3 classes.

### Eval Quality

- [ ] `quality` suite runnable; fails on linking/repair expect regressions.  
- [ ] Core suite still green in CI; heuristic off.  
- [ ] Report includes `repair_class_distribution` and linking-related summary fields where applicable.  
- [ ] Optional `llm` suite documented, not required for PR gate.

### Architecture

- [ ] No Kernel / Worker / Gate / Plane redesign.  
- [ ] No RAG / ReAct / Multi-Agent / Semantic Layer.  
- [ ] Fixed LangGraph (one new node max for linking).

---

## 7. Won't Do (this E1 phase)

| Won't Do | Reason |
|----------|--------|
| RAG / embeddings for schema | Drift + infra; linking is heuristic |
| ReAct / tool-calling repair agent | Conflicts with fixed graph |
| Multi-Agent (generator/critic) | Overbuild |
| Semantic Layer / metrics store product | Different product |
| Business glossary CMS | Optional later thin JSON only if needed |
| Infinite or budget-blind retry | Breaks cost/Run honesty |
| New Run `failure_class` for repair | Keep Worker taxonomy stable |
| Frontend Trace polish | Belongs to E2 |
| LLM-as-Judge Eval | Constraint/row_checks only |
| Changing SQL Gate allow rules to “pass more” | Safety first; repair fixes SQL, not Gate |

---

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Linking drops needed columns | Fallback_full; K configurable; Eval expects |
| Repair hint overfits Gate wording | Classifier tests on fixed strings |
| Graph change breaks Facade | Smoke kernel/agent + eval core |
| Scope creep into Semantic Layer | Stop-line in §7 |

---

## 9. Suggested implement order (after confirm)

```text
PR/slice 1: schema_linking module + graph node + prompt + smoke
PR/slice 2: repair_classify + validate/execute + prompt + smoke
PR/slice 3: eval quality suite + runner + release gate + baselines
```

Single combined PR allowed if kept thin; order above remains the dependency order.

---

## 10. Decision gate (human)

| Option | Meaning |
|--------|---------|
| **Confirm as written** | Implement A→B→C per this checklist |
| **Confirm A+B only** | Defer quality suite wiring to immediate follow-up |
| **Confirm linking-only first** | Smallest PR; repair/eval next |
| **Reject / revise** | Adjust K, enum, or graph shape before coding |

**Awaiting confirmation — no coding until approved.**
