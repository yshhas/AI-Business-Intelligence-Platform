# HITL H1 Implementation Report

**Sprint:** H1 — Lifecycle + wait terminals  
**Date:** 2026-07-22  
**Baseline:** v1.1.0 / `6d80ef3`  
**SSOT:** `docs/HITL_IMPLEMENTATION_PLAN.md` (+ Review Addendum R1–R8)  
**Status:** Implemented · **not committed** (await Review + commit auth)

**Out of scope (honored):** Approve→Execute · Resume Worker · H2 · FE polish

---

## 1. Delivered

| Item | Location |
|------|----------|
| Migration `0015_hitl_h1_awaiting_approval` | `require_sql_approval`, `approval_requested_at` |
| Lifecycle | `ACTIVE_STATUSES` + `awaiting_approval`; `FAILURE_HITL_REJECTED` |
| Kill-switch | `HITL_SQL_APPROVAL_ENABLED` / `hitl_sql_approval_enabled` (default **false**) |
| In-flight R5 | `count_running` = `running` ∪ `awaiting_approval` |
| Sweeper R1 | `expire_awaiting_approval` in Worker loop + idle path |
| Plan→wait | Agent `hitl_plan_only` + mock HITL plan; Worker `_mark_awaiting_approval` |
| API | Create `require_sql_approval`; `TaskOut` fields; `POST .../reject`; cancel-from-wait |
| Smoke | `scripts/smoke_hitl_h1.py` wired into Release Gate |
| Docs | `.env.example`, `OPS_CONFIG_MATRIX.md` |

## 2. Behavior summary

```text
HITL on + require_sql_approval + data.bi
  → plan (no Data Plane) → awaiting_approval
  → reject → failed/hitl_rejected
  → cancel → cancelled
  → sweeper timeout → timed_out

HITL off or non-data.bi → flag forced false → v1.1 path
```

**No approve route.** Resume/execute deferred to H2.

## 3. Verification

| Check | Result |
|-------|--------|
| `smoke_hitl_h1` | **HITL_H1_OK** |
| Release Gate | **PASS** (includes `smoke_hitl_h1`) |
| Eval core / quality / profile | **EVAL_OK** (flagless) |

## 4. Explicit non-delivery

- `POST .../approve`  
- Worker execute resume / SQL snapshot re-check suite  
- FE checkbox / banner  
- Gate-deny→never-wait dedicated agent smoke (covered by existing Eval gate denies + plan stop design)

## 5. Suggested commit (when authorized)

```text
feat(hitl): H1 awaiting_approval lifecycle, reject/cancel/timeout, kill-switch
```

---

**End of H1 Implementation Report.**
