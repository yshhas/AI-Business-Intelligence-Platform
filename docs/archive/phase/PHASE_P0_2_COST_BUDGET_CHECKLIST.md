# P0-2 — Soft Cost Budget Design Checklist

**Status:** ✅ Implemented & frozen (human confirmed 2026-07-22) — see [PHASE_P0_2_COST_BUDGET_ACCEPTANCE.md](PHASE_P0_2_COST_BUDGET_ACCEPTANCE.md)  
**Date:** 2026-07-22  
**Parent:** [PROJECT_IMPROVEMENT_PLAN.md](../roadmap/PROJECT_IMPROVEMENT_PLAN.md) · P0-1 frozen  
**Architecture lock:** `Skill → Policy → Data Plane → Trace`  
**Shell ownership:** Cost control lives in **Product Shell / Worker edges**, not Kernel.

---

## 0. Goal

Turn existing LLM **usage Trace** into a **soft control**: when a workspace exceeds a configured daily token budget, **new Analyze enqueues are rejected** with an honest failure class — without building FinOps, billing, or model-routing products.

| In | Out (this phase) |
|----|------------------|
| Soft daily token budget (workspace-scoped) | Cost dashboard UI product |
| Enqueue gate + 429 | Hard-kill of in-flight Runs |
| Sum usage from completed Runs / steps | Exact multi-currency billing |
| Settings switch (`0` = off) | Model routing / provider arbitrage |
| Smoke + OPS matrix | Prompt CMS / cost ML |

**Design motto:** prove “over-budget can be refused,” then (P1) polish visibility — not the reverse.

---

## 1. Current state (as-is)

| Asset | Location | Gap |
|-------|----------|-----|
| Per-call usage | `LLMCallResult.usage` → step `output_json.llm.usage` | Not aggregated for policy |
| Step aggregation helper | `pipeline._merge_llm_metas` | Per-step only |
| Capacity enqueue gate | `runtime_essentials.assert_enqueue_allowed` | In-flight / queue depth only — **not tokens** |
| failure_class vocabulary | `run_lifecycle.py` | No `budget_rejected` yet |

**Nothing in Kernel needs to change** for soft budget.

---

## 2. Proposed control model

```text
Settings: LLM_TOKEN_BUDGET_PER_WORKSPACE_DAY
          (0 = disabled; default 0 for backward-compatible Demo)

On create_task (before Redis enqueue):
  used = sum(tokens for workspace, UTC calendar day, completed Runs with usage)
  if budget > 0 and used >= budget:
      → HTTP 429
      → task may be marked failed with failure_class=budget_rejected
        (mirror capacity_rejected pattern)
  else:
      → enqueue as today
```

### Soft semantics (honest limits)

| Behavior | Choice |
|----------|--------|
| What is counted? | **Finished** Runs only (`succeeded` / `failed` / `cancelled` / `timed_out`) that recorded usage |
| In-flight Runs | **Not** pre-reserved → workspace can briefly exceed budget (soft) |
| Day boundary | **UTC** midnight (document; no per-tenant TZ product) |
| Unit | `total_tokens` (fallback: `prompt + completion` if total missing) |
| Missing usage | Count as **0** (heuristic / no-LLM Runs do not consume budget) |
| Disable | `LLM_TOKEN_BUDGET_PER_WORKSPACE_DAY=0` → identical to today |

---

## 3. Data design

### 3.1 Preferred: denormalized column (thin migration)

Add to `analysis_tasks`:

| Column | Type | Meaning |
|--------|------|---------|
| `llm_total_tokens` | `Integer NULL` | Sum of LLM `total_tokens` for this Run; set by Worker on terminal persist |

**Why:** cheap `SUM` for workspace+day without JSON scan; aligns with Trace honesty (value derived from steps at finish).

Worker (on success/fail path when persisting steps/result):

1. Walk `AgentRunStep.output_json.llm.usage` (and merged metas).  
2. Sum `total_tokens` (or prompt+completion).  
3. Set `task.llm_total_tokens`.  
4. Optionally echo into `result_json.platform.run.llm_total_tokens` / execution summary (additive Trace field — **not** a Kernel API break).

### 3.2 Aggregation query (Shell)

```text
SUM(llm_total_tokens)
FROM analysis_tasks
WHERE workspace_id = ?
  AND created_at >= utc_day_start
  AND created_at <  utc_day_end
  AND llm_total_tokens IS NOT NULL
```

Use `created_at` (enqueue day) so budget maps to “asks started today,” not finish day (document this choice).

### 3.3 Alternative (if migration deferred)

Scan `agent_run_steps.output_json` for workspace tasks today — OK for Demo scale; slower; prefer column if one migration is acceptable.

**Recommendation:** **do the thin column** (Alembic `0010_…`) — one migration, clearer smoke, better CI.

---

## 4. failure_class & API behavior

| Item | Value |
|------|-------|
| New class | `budget_rejected` (add to `run_lifecycle` constants) |
| HTTP | `429` (same family as `capacity_rejected`) |
| Message | Clear: workspace daily LLM token budget exceeded; used/budget in detail |
| Enqueue | Must **not** LPUSH if rejected after task row created → follow capacity pattern (mark failed + no queue / or fail before insert — **prefer check before insert** when possible; if row exists, mark terminal like capacity) |

**Suggested order in `create_task`:**

1. permission / skill lifecycle  
2. capacity (`assert_enqueue_allowed`)  
3. **budget (`assert_budget_allowed`)** ← new  
4. insert + enqueue  

---

## 5. Code impact scope

### In scope

| Path | Change |
|------|--------|
| `backend/app/core/config.py` | `llm_token_budget_per_workspace_day: int = 0` |
| `.env.example` · `OPS_CONFIG_MATRIX.md` | Document setting |
| `backend/alembic/versions/0010_*.py` | `llm_total_tokens` column |
| `backend/app/models/__init__.py` | Field on `AnalysisTask` |
| `backend/app/services/cost_budget.py` | **NEW** — sum used + assert gate |
| `backend/app/services/run_lifecycle.py` | `FAILURE_BUDGET = "budget_rejected"` |
| `backend/app/services/task_service.py` | Call budget assert |
| `backend/app/workers/analysis_worker.py` | Persist `llm_total_tokens` from steps |
| `backend/scripts/smoke_p0_2_cost_budget.py` | **NEW** smoke |
| `smoke_release_gate.py` | Include smoke when appropriate |
| Schemas / TaskOut (optional thin) | Expose `llm_total_tokens` read-only |

### Explicitly out

| Path / theme | Why |
|--------------|-----|
| `agent/kernel/**` | Boundary freeze |
| Model routing / multi-provider | P2+ |
| Cost dashboard / charts UI | P1-4 |
| Per-user quotas, tenant bills | Overbuild |
| Hard abort running LLM | Cooperative timeout already exists; not FinOps kill |
| Redis token bucket for HTTP | Separate from Run budget |
| Changing Eval / Prompt | Orthogonal |

---

## 6. Trace / Observability

| Signal | Where |
|--------|-------|
| Per-Run tokens | `analysis_tasks.llm_total_tokens` + optional `platform.run.llm_total_tokens` |
| Reject log | `log_run(..., failure_class=budget_rejected)` |
| Budget remaining (optional) | Only in 429 detail / log — **not** required on every TaskOut in P0-2 |

SSE: no token streaming; budget reject happens **before** Run starts → client sees create failure / failed task, same as capacity.

---

## 7. Smoke / acceptance (planned)

`smoke_p0_2_cost_budget.py` (design):

1. Budget `0` → create path unchanged (or unit-level assert skip).  
2. Seed workspace usage ≥ budget (direct DB update of `llm_total_tokens` on a fake finished task **or** inject via service test double).  
3. `create_task` → 429 / `budget_rejected`.  
4. Raise budget / clear usage → create succeeds again.  
5. Worker path: after a mock/agent step with usage meta, `llm_total_tokens` populated (minimal fixture).

Gate: add to `smoke_release_gate` after P0-1 eval (platform + quality + cost honesty).

---

## 8. Acceptance criteria (for later implement)

- [ ] Setting `0` preserves today’s enqueue behavior.  
- [ ] Setting `N>0` blocks new enqueue when workspace UTC-day sum ≥ N.  
- [ ] Response is 429 with `failure_class=budget_rejected` (task terminal if row created).  
- [ ] Completed Runs persist `llm_total_tokens` from step usage when present.  
- [ ] Missing usage → 0 contribution (no false blocks from heuristic-only Runs).  
- [ ] Soft overrun of in-flight documented; no hard-kill.  
- [ ] No Kernel / Policy / Plane / Eval architecture change.  
- [ ] No cost UI, routing, or billing engine.  
- [ ] Smoke + OPS matrix updated; release gate includes smoke.

---

## 9. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| JSON-only SUM too slow | Prefer denormalized column |
| UTC vs local day confusion | Document UTC; no TZ product |
| Soft overrun surprises | Document; optional P1 “estimate reserve” later |
| Double-count retries inside one Run | Sum steps once per Run into `llm_total_tokens` |
| Capacity vs budget confusion | Distinct `failure_class`; clear error strings |

---

## 10. Relationship to Roadmap

| Phase | Role |
|-------|------|
| **P0-1 Eval** | Prove quality regressions (done) |
| **P0-2 Soft Budget** | Prove cost can be refused (this checklist) |
| **P1-4 Cost rollup UI** | Show used/budget on Analyze / Tasks |
| **P2** | Routing / async LLM only with evidence |

---

## 11. Implementation checklist (only after confirm)

### Design lock

- [ ] Human confirms: **workspace + UTC day + soft enqueue reject**  
- [ ] Human confirms: **thin `llm_total_tokens` migration** (recommended) vs JSON-scan-only  
- [ ] Human confirms: default budget **0** (off)

### Build (not started)

- [ ] Migration + model  
- [ ] `cost_budget.py` + task_service + worker persist  
- [ ] Smoke + release gate  
- [ ] Acceptance / freeze docs  

### Stop-line

- [ ] No FinOps dashboard as phase goal  
- [ ] No model router  
- [ ] No Kernel budget policy engine  

---

## 12. Decision gate (human)

| Option | Meaning |
|--------|---------|
| **Confirm as written** | Implement P0-2 per this checklist |
| **Confirm with edits** | e.g. global (not workspace) budget; or JSON-scan without migration |
| **Reject / revise** | Adjust before coding |

**Awaiting confirmation — no coding until approved.**
