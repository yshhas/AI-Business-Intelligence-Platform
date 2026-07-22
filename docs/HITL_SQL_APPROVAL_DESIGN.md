# HITL SQL Approval Design (Design-only)

**Status:** Design ADR · **Non-goal for v1.1 code**  
**Sprint:** 3 (docs only)  
**Date:** 2026-07-22  

**Spine (unchanged):**  
`Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts`

---

## 1. Purpose

Enterprises often require a human to **review generated SQL** (and Gate outcome) before execution against a live RO plane. This document defines a future **Human-in-the-loop (HITL)** approval flow.

**This Sprint does not implement** any of the states, APIs, or Worker pauses described below.

---

## 2. Problem

Today `data.bi` Runs proceed: link → generate SQL → Policy Gate → execute → Trace.  
There is no pause for analyst sign-off. Cancel/timeout (P1.1) abort Runs but do not model “waiting for human.”

---

## 3. Proposed future states (not coded)

Extend Run lifecycle **later** (Phase 2 / separate auth) with something like:

| Status | Meaning |
|--------|---------|
| `pending` / `running` | Existing |
| **`awaiting_approval`** | SQL+Gate ready; execution not started (or rolled back to pre-execute) |
| `succeeded` / `failed` / `cancelled` / `timed_out` | Existing terminals |

**Invariant:** Only Worker may flip Run status. Skill never writes terminal status. HITL approve/reject are Shell → Worker commands.

---

## 4. Sequence (target design)

```text
Shell: POST /tasks (skill=data.bi, hitl_required?=true)  [future flag]
  → Worker claims Run
  → Kernel/Skill: link + SQL gen + Gate (no execute yet)
  → Worker: status=awaiting_approval; Trace shows proposed SQL + gate decision
Shell UI: analyst Approve | Reject
  → POST .../tasks/{id}/approve  |  .../reject
  → Worker: execute (approve) or fail/cancel with failure_class (reject)
```

Policy Gate still answers “may this SQL run?” — HITL answers “does a human want it to run now?”

---

## 5. API sketch (future — not implemented)

| Method | Path | Notes |
|--------|------|-------|
| POST | `/tasks/{id}/approve` | Owner/analyst; only if `awaiting_approval` |
| POST | `/tasks/{id}/reject` | Body: optional reason → `failure_class` e.g. `hitl_rejected` |
| GET | execution/trace | Already shows SQL — extend with `awaiting_approval` summary |

Create-task optional: `require_sql_approval: bool` (default false for back-compat).

---

## 6. UX notes (future)

- Analyze Run panel: banner “SQL awaiting approval” with SQL + Gate allow/deny.
- Approve continues; Reject ends Run honestly (no silent execute).
- Viewers: read-only Trace; cannot approve.

---

## 7. Interaction with P1.1 cancel / timeout

- Cancel while `awaiting_approval` → `cancelled` (same as today).
- Wall-clock timeout while waiting → prefer **`timed_out`** or extend timeout policy in a later design (document decision at implementation time).
- Write fence / cooperative cancel rules still apply; HITL must not reopen write after terminal.

---

## 8. Non-goals (v1.1 / Sprint 3)

1. **No code** for `awaiting_approval` or approve/reject routes.  
2. **No Worker lifecycle** changes in Sprint 3–4 unless separately authorized.  
3. Not a substitute for Policy Gate.  
4. Not Multi-Agent critic loops.  
5. Not Semantic Layer.  

**Implementation is blocked** until Phase 2 (or an explicit follow-on Sprint) authorizes status-machine work.

---

## 9. Acceptance for this document

- [x] States sketched  
- [x] Sequence + API sketch  
- [x] UX notes  
- [x] Cancel/timeout interaction called out  
- [x] Explicit Non-goal for v1.1 code  

---

## 10. References

- `docs/V2_IMPLEMENTATION_PLAN.md` Sprint 3 / Phase 2 HITL  
- `docs/ROADMAP_V2.md` G5 / D5  
- P1.1 cooperative cancel design  
