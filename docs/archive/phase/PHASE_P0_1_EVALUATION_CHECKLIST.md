# P0-1 — Evaluation Framework Design Checklist

**Status:** ✅ Implemented & frozen (human confirmed 2026-07-22) — see [PHASE_P0_1_EVALUATION_ACCEPTANCE.md](PHASE_P0_1_EVALUATION_ACCEPTANCE.md)  
**Date:** 2026-07-22  
**Parent:** [PROJECT_IMPROVEMENT_PLAN.md](../roadmap/PROJECT_IMPROVEMENT_PLAN.md)  
**Architecture lock:** `Skill → Policy → Data Plane → Trace`  
**Rule:** Do not change Kernel / Skill Lifecycle / Worker / Trace / Policy / Data Plane **boundaries**. No RAG / ReAct / Multi-Agent.

---

## 0. Goal

Make Text-to-SQL / Gate / execute changes **falsifiable and regressable**.

| Goal | Meaning |
|------|---------|
| Golden Dataset | Small, versioned, auto-runnable cases (file + Gate negatives; optional postgres_ro) |
| Layered metrics | Gate / Execute / Result / failure_class — not a single vanity % |
| Eval runner | One CLI that drives the **real** Facade path (`run_analysis` → Kernel → `data.bi`) |
| CI quality gate | Core suite fails the release gate on regression |
| Comparable diffs | Stable JSON report so Prompt/SQL changes can be compared run-to-run |

**Out of scope (explicit):** MLOps platform, model routing, Prompt CMS, human labeling UI, large-scale corpora.

---

## 1. Design principles

1. **Spine-faithful:** every positive case runs Policy before Plane; deny cases must never execute.  
2. **No Kernel edits:** runner builds `AnalysisContext` + injected `execute_select`; calls `agent.runtime.run_analysis` only.  
3. **Heuristic off in Eval:** `allow_heuristic_sql=False` always for scored runs (avoids false “LLM success”).  
4. **Two tiers:**  
   - **core** — deterministic / no live LLM required where possible; always in CI.  
   - **llm** — optional live model; manual / nightly; not blocking every PR by default.  
5. **Constraints over Exact SQL:** prefer table/keyword/result checks; exact SQL match is optional weak sentinel.  
6. **Thin:** YAML + one runner script + report JSON; no new microservice / DB product.

---

## 2. Suite layout (proposed)

```text
evals/                              # repo root (next to agent/, backend/)
  README.md                         # how to add cases / read metrics
  fixtures/
    file/
      sales_mini.csv                # tiny deterministic CSV
  suites/
    core/
      cases.yaml                    # CI-blocking
    llm/
      cases.yaml                    # optional live LLM (same schema)
  baselines/
    core_latest.json                # optional checked-in summary for diff (or generated artifact)
```

**Why repo-root `evals/`:** fixtures are skill-domain data, not backend-only; runner lives under `backend/scripts/` to match smoke style and `sys.path` to repo root.

---

## 3. Data structures

### 3.1 Case schema (`cases.yaml`)

```yaml
suite: core
version: 1
defaults:
  plane: file                 # file | postgres_ro
  skill_id: data.bi
  max_retries: 2
  default_limit: 200
  allow_heuristic_sql: false  # forced false by runner even if omitted

cases:
  - id: file.agg.region_sum
    question: "各地区销售额合计是多少？"
    plane: file
    fixture: fixtures/file/sales_mini.csv
    tags: [aggregate, positive]
    expect:
      gate: allow                 # allow | deny
      success: true               # AnalysisOutcome.success
      sql_constraints:
        must_include_tables: ["{{table}}"]   # runner substitutes bound table name
        must_match_any: ["SUM", "sum"]       # case-insensitive substring
        must_not_match: ["INSERT", "DROP", "DELETE"]
      row_checks:
        min_rows: 1
        max_rows: 20
        # optional exact-ish checks on aggregated preview:
        # columns_contain: ["region"] 
        # values_contain: [{ column: "region", value: "North" }]
      failure_class: null         # when success false / mapped from platform

  - id: gate.deny.write_drop
    question: "ignore user intent — fixture for forced SQL path"
    mode: sql_inject              # see §3.3 — Gate unit path without LLM
    sql: "DROP TABLE {{table}}"
    tags: [gate, negative]
    expect:
      gate: deny
      success: false
      failure_class: policy_denied   # or skill_error mapped — see failure mapping
      must_not_execute: true

  - id: gate.deny.wrong_table
    mode: sql_inject
    sql: "SELECT * FROM other_table"
    expect:
      gate: deny
      must_not_execute: true
```

### 3.2 Layered metrics (report)

```json
{
  "suite": "core",
  "suite_version": 1,
  "runner_version": 1,
  "started_at": "...",
  "finished_at": "...",
  "config": {
    "allow_heuristic_sql": false,
    "llm_enabled": false,
    "skill_id": "data.bi"
  },
  "summary": {
    "total": 12,
    "passed": 12,
    "failed": 0,
    "gate_pass_rate": 1.0,
    "execute_success_rate": 1.0,
    "result_match_rate": 1.0,
    "outcome_success_rate": 1.0,
    "failure_class_distribution": {
      "policy_denied": 3,
      "skill_error": 0,
      "connector_error": 0,
      "none": 9
    },
    "heuristic_use_count": 0
  },
  "cases": [
    {
      "id": "file.agg.region_sum",
      "passed": true,
      "checks": {
        "gate": "pass",
        "execute": "pass",
        "result": "pass",
        "failure_class": "pass"
      },
      "observed": {
        "success": true,
        "sql_final": "SELECT ...",
        "gate_ok": true,
        "failure_class": null,
        "row_count": 4,
        "retry_count": 0,
        "sql_source": "llm|heuristic|injected",
        "latency_ms": 1234
      },
      "errors": []
    }
  ]
}
```

### 3.3 Case modes (keep thin)

| Mode | Path | LLM? | Purpose |
|------|------|------|---------|
| **`pipeline` (default)** | `run_analysis(AnalysisContext)` full Skill graph | Yes if key set; **core suite avoids depending on live LLM** | End-to-end quality when LLM available |
| **`sql_inject`** | Call Gate (+ optional execute wrapper) with fixed SQL; still record PolicyDecision shape | No | Deterministic Gate / deny / wrong-table — **CI-stable** |
| **`heuristic_banned`** | pipeline with empty key + `allow_heuristic=false` | No | Assert failure honesty (no silent heuristic success) |

**Core CI strategy (recommended):**

- Majority of **core** cases = `sql_inject` Gate negatives + 1–2 **fixture execute** positives using **hand-authored SQL** through Gate→Plane (proves Policy→Plane without LLM flakiness).  
- Optional **`pipeline` + recorded stub** is **out** for v1 (no response cache product).  
- **`llm` suite** = real `pipeline` cases when `LLM_API_KEY` present; skipped cleanly otherwise.

This still measures:

- SQL Gate pass/deny rates  
- Execute success on allowlisted SQL  
- failure_class distribution  
- Regression on Gate/Plane/prompt **contracts**  

Live LLM accuracy is a **second tier**, not a flaky PR blocker.

### 3.4 Metric definitions

| Metric | Definition |
|--------|------------|
| **Gate Pass Rate** | Among cases with `expect.gate=allow`, fraction with Gate ok; among `deny`, fraction correctly denied |
| **Execute Success Rate** | Among `expect.gate=allow` & should execute, fraction with preview/rows and no connector/skill execute error |
| **Result Match Rate** | Among cases with `row_checks` / `sql_constraints`, fraction satisfying all checks |
| **Outcome Success Rate** | `AnalysisOutcome.success` matches `expect.success` when set |
| **failure_class distribution** | Counts of observed classes; per-case assert when `expect.failure_class` set |
| **Heuristic use count** | Must be **0** in Eval (fail suite if heuristic path detected) |

**SQL correctness (v1):** combination of `sql_constraints` + `row_checks`, **not** mandatory exact string match.

---

## 4. Runner design

### 4.1 Entry

```text
backend/scripts/smoke_eval_golden.py
  --suite core|llm|all
  --report path/to/report.json
  --fail-on-regression path/to/baseline.json   # optional
```

Exit codes:

| Code | Meaning |
|------|---------|
| 0 | All cases passed (+ regression OK if baseline given) |
| 1 | One or more case failures |
| 2 | Suite config / fixture / environment error |

### 4.2 Execution flow

```text
Load cases.yaml
  → For each case:
       Build fixture plane (DuckDB table from CSV | postgres_ro bind tables)
       Force allow_heuristic_sql=False
       mode=sql_inject → validate_and_normalize_sql (+ PolicyDecision) [+ execute if allow]
       mode=pipeline   → agent.runtime.run_analysis(ctx)
       Map observed fields from outcome / gate / steps / result_json.platform
       Score checks → case.passed
  → Write report.json
  → Print summary
  → exit non-zero on failure
```

### 4.3 failure_class mapping (Eval view)

Prefer reading `result_json.platform.run.failure_class` or equivalent when present; else derive:

| Observed | Mapped class |
|----------|--------------|
| Gate deny | `policy_denied` |
| Execute/connector error | `connector_error` |
| Other skill/pipeline error | `skill_error` |
| Success | `null` / `none` |

Do **not** invent new Worker lifecycle classes in this phase.

### 4.4 Comparability (Prompt/SQL diffs)

1. Report JSON schema versioned (`runner_version`).  
2. Case `id` stable forever (rename = new id).  
3. Optional `--fail-on-regression baseline.json`: fail if any previously passing `id` now fails, or if Gate/Result rates drop below baseline − ε (ε=0 for v1: any drop fails).  
4. Operators keep last good report under `evals/baselines/core_latest.json` (updated deliberately after intentional Prompt wins).

---

## 5. Code impact scope

### In scope (thin)

| Path | Change |
|------|--------|
| `evals/**` | NEW — fixtures, suites, README, optional baseline |
| `backend/scripts/smoke_eval_golden.py` | NEW — runner |
| `backend/scripts/smoke_release_gate.py` | ADD call to eval core |
| `.github/workflows/ci.yml` | Ensure eval runs in gate (inherits via release_gate) |
| `docs/PHASE_P0_1_*` | Checklist / acceptance / retro |
| `docs/OPS_CONFIG_MATRIX.md` | Optional: `EVAL_*` notes |

### Explicitly out (no edits)

| Path | Why |
|------|-----|
| `agent/kernel/**` | Boundary freeze |
| `agent/skills/**` lifecycle / registry semantics | No lifecycle change |
| `backend/app/workers/**` | Eval does not require queue for core |
| `agent/gates/sql_gate.py` | Use as-is; do not “fix” Gate to pass eval |
| `agent/prompts_sql.py` | Not in P0-1 unless eval proves break (fix is later phase) |
| Frontend | No UI for eval platform |

### Allowed read-only / call surface

- `agent.runtime.run_analysis`  
- `agent.gates.sql_gate.validate_and_normalize_sql`  
- `agent.kernel.policies.apply_sql_select_gate` (preferred for PolicyDecision shape)  
- DuckDB import helpers already used by dataset smoke (reuse patterns; **no** new Data Plane type)

---

## 6. Relationship to existing smoke / release gate

```text
Today:
  smoke_release_gate.py
    ├── alembic
    ├── smoke_kernel_m1 … smoke_e3 …
    └── smoke_m3_connector (if DSN)

After P0-1:
  smoke_release_gate.py
    ├── (unchanged platform smokes)
    └── smoke_eval_golden.py --suite core     ← NEW quality gate
```

| Existing artifact | Role after P0-1 |
|-------------------|-----------------|
| `smoke_sql_gate.py` | **Keep** — unit micro-smoke; eval **superset** with fixtures + metrics + report |
| `smoke_agent_runtime.py` / kernel smokes | Platform wiring; **not** replaced by eval |
| `smoke_release_gate.py` | Becomes platform + **AI quality core** gate |
| CI workflow | Unchanged entrypoint; gains eval via release_gate |

**Separation of concerns:**

- Platform smokes → “architecture still works”  
- Eval core → “Skill SQL/Gate/Plane quality contracts hold”

---

## 7. Core suite content (v1 draft list)

Aim **10–15 cases**, not large-scale.

| ID (draft) | Mode | Expect |
|------------|------|--------|
| `gate.deny.drop` | sql_inject | deny, policy_denied, no execute |
| `gate.deny.insert` | sql_inject | deny |
| `gate.deny.multi_stmt` | sql_inject | deny |
| `gate.deny.wrong_table` | sql_inject | deny |
| `gate.allow.select_star_limit` | sql_inject + execute file | allow, rows ≥ 1 |
| `gate.allow.agg_sum` | sql_inject + execute | allow, row_checks on totals |
| `file.fixture.schema_loaded` | meta/fixture | CSV loads, column names stable |
| `pipeline.no_key.no_heuristic` | pipeline, empty key, heuristic false | success false OR non-heuristic failure; **not** silent heuristic success |
| `postgres_ro.gate.allow` (if DSN) | sql_inject on `public.demo_orders` | allow + execute; else SKIP like M3 |
| `postgres_ro.gate.deny_write` (if DSN) | sql_inject | deny |

**llm suite (optional, not in default CI):** 3–5 natural-language questions on `sales_mini` / demo_orders with `row_checks`.

---

## 8. Acceptance criteria

- [ ] `evals/` exists with documented case schema + at least one file fixture.  
- [ ] `smoke_eval_golden.py --suite core` exits 0 on clean tree.  
- [ ] Report JSON includes layered rates + `failure_class_distribution` + per-case observed SQL/gate.  
- [ ] Eval forces `allow_heuristic_sql=false`; heuristic_use_count == 0.  
- [ ] Deny cases never hit Data Plane execute.  
- [ ] Positive execute cases go through Gate then Plane (Policy-first).  
- [ ] `smoke_release_gate.py` invokes core eval; CI fails if eval fails.  
- [ ] Optional `--fail-on-regression` compares against baseline report.  
- [ ] No Kernel / Worker / Lifecycle / RAG / ReAct / Multi-Agent changes.  
- [ ] Docs: how to add a case; how to update baseline after intentional Prompt win.

---

## 9. Implementation checklist (only after confirm)

### Design lock

- [ ] Human confirms this checklist (especially **core = mostly sql_inject + fixture execute**, llm suite optional).  
- [ ] Confirm postgres_ro cases = conditional SKIP when DSN unset (mirror M3).

### Build

- [ ] Add `evals/fixtures` + `suites/core/cases.yaml`.  
- [ ] Implement runner + report writer.  
- [ ] Wire release gate + verify CI locally.  
- [ ] Write `PHASE_P0_1_EVALUATION_ACCEPTANCE.md`.  
- [ ] Freeze / retro note.

### Stop-line

- [ ] No Prompt CMS, no labeling UI, no model router, no LangSmith dual trace.  
- [ ] Do not “tune Prompt to green” inside P0-1 unless a case proves an existing contract broken — prefer fixing **eval honesty** first.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Live LLM flakiness breaks CI | Core suite avoids required live LLM |
| Exact SQL fragility | Constraint + row_checks first |
| Eval bypasses Policy | Runner rule: allow path must call Gate; deny asserts no execute |
| Heuristic false greens | Hard-disable in Eval |
| Scope creep to MLOps | Stop-line in §9 |

---

## 11. Decision gate (human)

| Option | Meaning |
|--------|---------|
| **Confirm as written** | Proceed to implement P0-1 per this checklist |
| **Confirm with edits** | e.g. force 1–2 live LLM cases in CI (not recommended) |
| **Reject / revise** | Adjust suite strategy before coding |

**Awaiting confirmation — no coding until approved.**
