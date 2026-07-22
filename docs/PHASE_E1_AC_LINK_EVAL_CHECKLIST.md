# E1-AC — Schema Linking Lite + Eval Quality (Final Implementation Checklist)

**Status:** ✅ **FROZEN** — [PHASE_E1_AC_FINAL_STATUS.md](./PHASE_E1_AC_FINAL_STATUS.md) · [ACCEPTANCE](./PHASE_E1_AC_ACCEPTANCE.md)  
**Date:** 2026-07-22  
**Parent:** [PHASE_E1_SQL_QUALITY_CHECKLIST.md](./PHASE_E1_SQL_QUALITY_CHECKLIST.md) · [ENHANCEMENT_ROADMAP.md](./ENHANCEMENT_ROADMAP.md)  
**Scope this round:** **A + C only** · **B (SQL Repair) deferred / evidence-gated**

---

## 0. Decision lock

| Item | Decision |
|------|----------|
| Implement now | **A** Schema Linking Lite + **C** Eval Quality extension |
| Defer | **B** SQL Repair (wait for quality baseline / Eval evidence) |
| Why A before B | Largest gap is **pre-generate schema understanding observability**, not post-fail patching |
| Why C with A | Linking fields must be **scorable and comparable** from day one |

### Constraints (binding)

1. No Kernel / Worker / Policy / Data Plane boundary changes.  
2. No change to existing Run `failure_class` semantics.  
3. Schema Linking outcomes must be **observable + classified** — **no silent fallback**.  
4. New fields must appear in **Eval reports** for before/after comparison.  
5. Eval keeps `allow_heuristic_sql=false`.

### Explicitly not in this round

- SQL Repair / `repair_class` / richer retry hints (Slice B)  
- RAG / ReAct / Multi-Agent / Semantic Layer  
- Frontend Trace polish (E2)  
- Changing Gate allow rules or Worker lifecycle  

---

## 1. Slice A — Schema Linking Lite (final)

### 1.1 Graph

```text
load_context → link_schema → generate_sql → validate_sql → …
```

- One new LangGraph node: `link_schema`.  
- Pure linker module (no LLM): e.g. `agent/schema_linking.py`.

### 1.2 Linking algorithm (v1)

| Input | `question`, full `schema`, primary `duckdb_table`, `allowed_tables` |
|-------|----------------------------------------------------------------------|
| Ranking | Deterministic token/name overlap + simple dim/metric name hints |
| Cap | `SCHEMA_LINK_MAX_COLUMNS` (default **12**, via AnalysisContext or settings passed in hints — **Skill-local**, not Kernel) |
| Primary table | **Always** included in `selected_tables` |

### 1.3 Observable classification — **no silent fallback**

Every run **must** emit a `link_schema` step with an explicit status. Recovery paths are labeled, never hidden.

| `link_status` | Meaning | Prompt schema used |
|---------------|---------|---------------------|
| `ok` | Overlap produced a non-empty linked column set within K | `selected_columns` |
| `partial` | Some signals matched but coverage weak (e.g. &lt; 2 cols or only primary key-like) — still uses linked set | `selected_columns` |
| `fallback_full` | **Explicit** recovery: linker chose full schema (or first K of full) because overlap empty / ambiguous | full or capped-full columns; **must** set this status |
| `failed` | Linker could not produce a usable schema view (e.g. empty schema input) | generate_sql should see failure; pipeline may fail early **or** still generate with empty cols + `failed` visible — prefer **fail closed on empty schema**; for empty overlap use `fallback_full` not `failed` |

**Forbidden:** using full schema in the prompt while reporting `link_status=ok` or omitting `link_schema` step.

| `link_method` | Examples |
|---------------|----------|
| `token_overlap` | Default scorer |
| `fallback_full` | Paired with `link_status=fallback_full` |
| `identity` | Schema already ≤ K (no reduction); still `ok` if non-empty |

Optional: `link_reason` short string (e.g. `no_token_overlap`, `schema_empty`, `within_k_noop`).

### 1.4 Prompt contract

- `build_text_to_sql_prompts` receives **linked** column list for the primary table.  
- Always still lists `allowed_tables` (Policy honesty).  
- User/system text may note `link_status` when not `ok` (one line) so the model is not lied to.

### 1.5 A implementation checklist

- [ ] `agent/schema_linking.py` — `link_schema(question, schema, table, allowed_tables, max_columns) -> LinkResult`  
- [ ] `LinkResult` fields: status, method, reason, selected_tables, selected_columns, scores (optional)  
- [ ] `agent/state.py` — state keys for link fields  
- [ ] `agent/graph.py` — insert `link_schema` node  
- [ ] `agent/nodes/pipeline.py` — node + step emit  
- [ ] `agent/prompts_sql.py` — consume linked columns + status note  
- [ ] Project `platform.sql_quality` (see §2) from Skill/Facade path  
- [ ] Unit/smoke: deterministic fixtures for `ok` / `fallback_full` / `failed`  
- [ ] **No** changes to `sql_gate.py`, Worker lifecycle, Kernel runtime  

---

## 2. Trace field definition (final)

### 2.1 Step: `link_schema`

```json
{
  "node_name": "link_schema",
  "status": "ok" | "error",
  "output_json": {
    "link_status": "ok | partial | fallback_full | failed",
    "link_method": "token_overlap | fallback_full | identity",
    "link_reason": "string|null",
    "selected_tables": ["…"],
    "selected_columns": ["…"],
    "column_count_full": 20,
    "column_count_linked": 8
  }
}
```

- Step `status=error` only when `link_status=failed` (unusable schema).  
- `fallback_full` → step `status=ok` **with** explicit `link_status=fallback_full` (observability, not silence).

### 2.2 `platform.sql_quality` (audit projection)

```json
"platform": {
  "sql_quality": {
    "schema_version": 1,
    "link_status": "ok",
    "link_method": "token_overlap",
    "link_reason": null,
    "selected_tables": ["ds_…"],
    "selected_columns": ["region", "amount", "…"],
    "column_count_full": 20,
    "column_count_linked": 8
  }
}
```

| Rule | |
|------|--|
| Purpose | Audit / explain / Eval — **not** a Gate or ACL cache |
| Writer | Skill/`data.bi` result projection (Facade path), not Kernel RBAC |
| Absent | Only for non-pipeline runtimes (mock); agent path should always set when link ran |

### 2.3 State fields

```text
selected_tables: list[str]
selected_columns: list[str]
link_status: str
link_method: str
link_reason: str | None
```

---

## 3. Slice C — Eval metrics & suite changes (final)

### 3.1 Suites

| Suite | CI release gate? | Role |
|-------|------------------|------|
| `core` | **Yes** | Keep Gate/execute/honesty; add **deterministic link cases** (`mode: link_only` and/or pipeline expects) |
| `quality` | **Yes** if fully deterministic (recommended) | Linking expects + regression on `link_status` / columns |
| `llm` | **No** (manual/nightly) | NL accuracy; still heuristic off |

### 3.2 New case expects

```yaml
mode: link_only   # run linker only; no LLM
expect:
  link_status: ok                 # or fallback_full | failed | partial
  link_method_in: [token_overlap, identity]
  selected_columns_contain: [region, amount]
  selected_columns_exclude: [unrelated_wide_col]   # optional
  selected_tables_contain: ["{{table}}"]
```

Pipeline cases (optional in quality):

```yaml
mode: pipeline
expect:
  link_status_in: [ok, partial, fallback_full]   # must be present; never missing
  # existing success/heuristic_forbidden rules unchanged
```

### 3.3 Report `summary` additions

```json
"summary": {
  "link_status_distribution": {
    "ok": 5,
    "partial": 1,
    "fallback_full": 2,
    "failed": 0
  },
  "link_ok_rate": 0.625,
  "link_fallback_rate": 0.25,
  "link_failed_rate": 0.0,
  "schema_link_cases": 8,
  "schema_link_passed": 8
}
```

| Metric | Definition |
|--------|------------|
| `link_status_distribution` | Counts of observed `link_status` among scored link-aware cases |
| `link_ok_rate` | `ok` / link-aware cases (optional exclude `identity`-only if desired — **v1: include all**) |
| `link_fallback_rate` | `fallback_full` / link-aware cases — **explicit quality signal** (higher ≠ silent) |
| `link_failed_rate` | `failed` / link-aware cases |
| Existing rates | Gate / execute / result / heuristic_use unchanged |

**Comparability:** `--fail-on-regression` should treat drop in `schema_link_passed` / newly failing link expects as regression; optional: fail if `link_failed_rate` rises vs baseline.

### 3.4 C implementation checklist

- [ ] `evals/runner.py` — `link_only` mode + expect scorers + summary metrics  
- [ ] `evals/suites/quality/cases.yaml` — fixtures covering `ok`, `fallback_full`, `failed` (empty schema), `partial` if easy  
- [ ] Core: ≥1 link_only case or import quality into gate  
- [ ] `smoke_eval_golden.py --suite quality`  
- [ ] Release gate invokes `quality` (deterministic) after core  
- [ ] Baseline update path documented (`evals/baselines/quality_latest.json` optional)  
- [ ] Heuristic forced false everywhere in Eval  

---

## 4. Acceptance smoke design

### 4.1 `smoke_schema_linking.py` (unit / Skill-local)

| Case | Setup | Expect |
|------|--------|--------|
| S1 | Question mentions `region`/`amount`; schema has those + noise cols | `link_status=ok` (or `partial`), `selected_columns` contain region/amount, exclude at least one noise if K tight |
| S2 | Question with **no** overlapping tokens vs column names | `link_status=fallback_full`, `link_method=fallback_full`, step present |
| S3 | Empty schema list | `link_status=failed`, observable error |
| S4 | Schema length ≤ K | `link_method=identity` or `ok`, all cols selected |

Print `SCHEMA_LINKING_OK` on success.

### 4.2 `smoke_eval_golden.py --suite quality`

| Case ids (draft) | Mode | Expect |
|------------------|------|--------|
| `link.ok.region_amount` | link_only | status ok + columns contain |
| `link.fallback.no_overlap` | link_only | fallback_full |
| `link.failed.empty_schema` | link_only | failed |
| `link.identity.small_schema` | link_only | ok/identity |

Exit non-zero on expect miss; report includes `link_*` summary fields.

### 4.3 Release gate

```text
… existing smokes …
smoke_schema_linking.py
smoke_eval_golden --suite core [--fail-on-regression core baseline]
smoke_eval_golden --suite quality [--fail-on-regression quality baseline if present]
```

### 4.4 Regression / before-after

1. Land A+C with quality baseline committed when green.  
2. Later Prompt/linking tweaks: compare `link_ok_rate` / `link_fallback_rate` / case pass in report JSON.  
3. **Do not** “fix” quality by silencing fallback — reduce `fallback_full` rate via better overlap, measurable in Eval.

---

## 5. Impact file range (A+C only)

| Path | Action |
|------|--------|
| `agent/schema_linking.py` | NEW |
| `agent/state.py` | link fields |
| `agent/graph.py` | edge via `link_schema` |
| `agent/nodes/pipeline.py` | `link_schema` node |
| `agent/prompts_sql.py` | linked columns + status note |
| `agent/skills/data_bi/skill.py` and/or Facade projection | `platform.sql_quality` |
| `evals/runner.py` | link_only + metrics |
| `evals/suites/quality/cases.yaml` | NEW |
| `evals/suites/core/cases.yaml` | optional 1–2 link asserts |
| `evals/baselines/quality_latest.json` | after first green |
| `backend/scripts/smoke_schema_linking.py` | NEW |
| `backend/scripts/smoke_eval_golden.py` | `--suite quality` |
| `backend/scripts/smoke_release_gate.py` | wire smokes |
| `docs/PHASE_E1_AC_ACCEPTANCE.md` | after implement |

**Out:** `repair_classify.py`, Gate, Worker lifecycle, Kernel, frontend, permissions, cost_budget.

---

## 6. Acceptance criteria (gate to “done”)

- [ ] `link_schema` always runs on `data.bi` agent pipeline; step always present.  
- [ ] No silent full-schema use: recovery ⇒ `link_status=fallback_full` (or `failed`).  
- [ ] `platform.sql_quality` populated on agent runs with link fields.  
- [ ] `smoke_schema_linking.py` passes (S1–S4).  
- [ ] `smoke_eval_golden --suite quality` passes; report has `link_status_distribution` + rates.  
- [ ] Release gate runs schema-link smoke + quality suite.  
- [ ] Core Eval still green; heuristic_use_count == 0.  
- [ ] `failure_class` vocabulary unchanged; no Slice B repair.  
- [ ] Kernel / Worker / Policy / Plane untouched in responsibility.

---

## 7. Decision gate

| Option | Meaning |
|--------|---------|
| **Confirm A+C as written** | Proceed to implement this checklist |
| **Revise link_status taxonomy** | Adjust enums before coding |
| **Quality suite not in CI yet** | Only smoke_schema_linking in gate (not preferred) |

**Awaiting confirmation — no coding until approved.**
