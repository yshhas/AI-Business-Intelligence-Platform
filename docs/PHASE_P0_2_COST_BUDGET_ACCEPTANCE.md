# P0-2 Soft Cost Budget — Acceptance

**Status:** ✅ **Frozen / complete** (human confirmed 2026-07-22)  
**Date:** 2026-07-22  
**Checklist:** [PHASE_P0_2_COST_BUDGET_CHECKLIST.md](./PHASE_P0_2_COST_BUDGET_CHECKLIST.md)

## Goals achieved

- [x] Workspace-level token usage constraint  
- [x] Budget check **before enqueue** (govern before execute)  
- [x] Over-budget never enters Worker / Skill path  
- [x] Trace/Step remain detail truth; `llm_total_tokens` is aggregate only  
- [x] Default off (`0`) — no behavior change when unset  
- [x] No billing system; Kernel / Worker / Policy boundaries unchanged  

## Confirmed decisions (implemented)

| Decision | Implementation |
|----------|----------------|
| Workspace + UTC day + soft enqueue check | `cost_budget.assert_budget_allowed` before Redis push |
| HTTP 429 + `budget_rejected` | `TaskServiceError(429)` + audit task row |
| No in-flight kill | Gate only on `create_task` |
| `llm_total_tokens` column | Alembic `0010_p0_2_cost_budget` |
| Default budget `0` | `Settings.llm_token_budget_per_workspace_day = 0` |
| No Cost UI / FinOps / routing / Kernel change | Shell + Worker persist only |

## Migration / check / smoke (shipped)

- Migration: `0010_p0_2_cost_budget`  
- Gate: `task_service.create_task` → `cost_budget.assert_budget_allowed`  
- Persist: Worker `_finalize_tokens`  
- Smoke: `smoke_p0_2_cost_budget.py` in release gate  

## Follow-ups (recorded — **not** opened for coding)

### 1. What Cost Control covers today

- Token consumption observation (steps + `llm_total_tokens`)  
- Workspace UTC-day soft budget protection  

**Later (only if real usage demands):** cost rollup display · finer workspace/dataset permission strategies · model-level cost policy — each as a thin authorized slice.

### 2. Standing principles

- Cost Control = **governance**, not a FinOps platform  
- Do **not** introduce model routing, auto degrade, or complex budget suites in this arc  

## Out of scope (held)

Cost UI · FinOps · model routing · auto degrade · budget admin console · Kernel budget policy  

**Next:** [PHASE_P1_PERMISSION_GOVERNANCE_CHECKLIST.md](./PHASE_P1_PERMISSION_GOVERNANCE_CHECKLIST.md) (design only until confirmed).
