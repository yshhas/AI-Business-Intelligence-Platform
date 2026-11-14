# HITL Implementation Plan Review

**Review type:** Read-only Implementation Plan Review (no coding)  
**Date:** 2026-07-22  
**SSOT under review:** `docs/HITL_IMPLEMENTATION_PLAN.md`  
**Baseline:** v1.1.0 / `6d80ef3`  
**Operator constraints:** Design-only · no commit · no push · no `v2.0.0` · next auth = **H1 only** (H2 after H1 Review)

---

## 0. Verdict

| Area | Result | Blocking for H1 auth? |
|------|--------|------------------------|
| State machine consistency | **PASS with locks** | Locks R1–R3 required |
| Data migration & rollback | **PASS** | No |
| API / OpenAPI compatibility | **PASS with locks** | Lock R4 |
| Worker lifecycle | **PASS with locks** | Locks R1, R5–R6 required |
| Kill switch | **PASS** | No |
| Smoke / Gate / Eval | **PASS with split** | Lock R7 (H1 vs H2 coverage) |
| Sprint H0→H4 split | **PASS** (endorse **H1-only** next) | Lock R8 |

**Overall:** **PASS WITH CONDITIONS**

The plan is coherent for a **v1.2.x MVP** and suitable to charter **H1** after the locks in §2 are treated as part of the SSOT (see Plan Review Addendum on the plan doc).

**Not authorized by this review:** coding · commit · push · H2 · tag.

**P0 defects:** none  
**P1 locks (must accept before H1):** R1–R8 below  
**P2 notes:** non-blocking polish

---

## 1. Checklist findings

### 1.1 State machine consistency — **PASS WITH LOCKS**

**Strengths**

- Clear separation: Gate deny → terminal; Gate allow → wait; human Approve/Reject/Cancel/Timeout.
- Single `task_id`; terminals unchanged; Skill never terminals.
- `awaiting_approval` length fits `String(20)`.

**Gaps / locks**

| ID | Issue | Lock |
|----|-------|------|
| **R1** | Plan says wait timeout uses wall clock, but today timeout is enforced only while Worker holds `_run_with_timeout`. After plan→wait, Worker **returns** — no thread watches the clock. | H1 must add a Worker-loop (or equivalent) **`expire_awaiting_approval` sweeper**: `awaiting_approval` + `now > started_at + timeout_seconds` → CAS `timed_out` / `failure_class=timeout`. Do **not** use `runtime_reclaimed` for wait. |
| **R2** | Mermaid nests `plan/execute` under `running` then edges `plan → awaiting_approval`, which can be misread as a stored status. | SSOT clarification: stored statuses are only the string table; `plan`/`execute` are **`platform.hitl.phase` only**. |
| **R3** | Reject/cancel-from-wait vs “Worker sole governor”. | **API CAS terminals** allowed for reject + cancel-from-wait (same pattern as pending cancel). **Approve must not execute in API thread** — only signal/enqueue Worker resume (H2). |

**In-flight vs code today:** `count_running` / `claim_allowed` currently count **only** `status=="running"`. Plan L4 requires wait to count → see **R5**.

### 1.2 Data migration & rollback — **PASS**

| Check | Assessment |
|-------|------------|
| Thin boolean column + default false | Compatible; safe backfill |
| No DB ENUM | Correct for current model |
| Rollback: kill-switch → cancel/timeout parked → revert commits | Sound; no force-push |
| Leave column in place on code revert | Acceptable |

**P2:** Prefer including `approval_requested_at` in H1 migration (helps ops/timeout clarity); optional actor columns may wait H2/H3.

**P2:** Document down-migration as optional; default false column is forward-compatible.

### 1.3 API / OpenAPI compatibility — **PASS WITH LOCKS**

| Check | Assessment |
|-------|------------|
| Additive create field default false | Back-compat OK |
| New approve/reject routes | Old clients unaffected |
| Kill-switch forces flag false | OK |
| Non-`data.bi` ignores flag | OK |

| ID | Issue | Lock |
|----|-------|------|
| **R4** | `TaskOut` must expose `require_sql_approval` (+ status may be `awaiting_approval`). FE cancel today only for `pending\|running`. | H1: schema/OpenAPI + list/get return flag; H1 or H3: cancel affordance includes `awaiting_approval`. Approve/reject OpenAPI in the Sprint that ships the route (**approve execute semantics → H2**). |

**Error matrix (confirm at impl):** 403 auth · 409 wrong status / double action · 404 unknown · kill-switch off → treat create flag as false; approve/reject → **409 or 404** (pick one in H1 and stick to it; recommend **409** with clear detail).

### 1.4 Worker lifecycle — **PASS WITH LOCKS**

| Check | Assessment |
|-------|------------|
| Plan mode without `execute_select` | Required; correct Spine placement |
| Fence closed on wait | Required (`write_allowed` today requires `running`) |
| Skip stale reclaim on wait | Correct (reclaim queries `running` only today — keep it that way) |
| Resume ≠ pending claim | Must not reuse `pending → running` CAS for approve |

| ID | Issue | Lock |
|----|-------|------|
| **R5** | Capacity: extend in-flight accounting to **`running` + `awaiting_approval`** (rename helper if needed). `pending` stays queue-depth gated only (current design). | H1 implements L4 in `runtime_essentials` |
| **R6** | Approve resume path | Dedicated resume: CAS `awaiting_approval → running` + `phase=execute` + re-enqueue/signal. **Full Skill execute + snapshot check = H2.** H1 must not claim DoD item “zero plane before approve” end-to-end without H2 — see R7/R8. |
| (with R1) | Wait timeout actor | Sweeper in Worker `run_forever` alongside reclaim |

### 1.5 Kill switch — **PASS**

| Check | Assessment |
|-------|------------|
| Default `false` | Safe |
| Create path forces off | Required |
| Rollback first lever | Correct |
| Mid-flight disable | Parked Runs still cancel/timeout; document in ops notes at impl |

**P2:** Expose flag to FE via existing boot/config surface (H3) so checkbox does not appear when disabled.

### 1.6 Smoke / Release Gate / Eval — **PASS WITH SPLIT**

Plan A5.6 lists approve→execute, reject, cancel, timeout, kill-switch, gate deny, snapshot mismatch in one suite. That spans **H1+H2**.

| ID | Lock |
|----|------|
| **R7** | **H1 smokes:** enter `awaiting_approval`; reject; cancel-while-waiting; timeout-while-waiting (sweeper); kill-switch off; gate deny never waits. **H2 smokes:** approve→execute; snapshot mismatch; Gate registration of full suite; Eval still flagless **EVAL_OK**. H1 may wire a **partial** gate entry or local smoke runner; **full Release Gate HITL suite green is H2 exit.** |

Eval: keep omitting HITL flag — **PASS** as written.

### 1.7 Sprint H0→H4 — **PASS** (H1-only next)

| Sprint | Review stance |
|--------|----------------|
| H0 | Done when this Review PASS WITH CONDITIONS accepted |
| **H1** | Lifecycle + API terminals from wait + plan→wait + sweeper + migration + kill-switch + H1 smokes — **authorize alone** |
| **H2** | Execute resume + Skill split + snapshot + full Gate — **only after H1 Implementation Review PASS** |
| H3 | FE + harden + Implementation Review |
| H4 | Audit + v1.2.x decision |

| ID | Lock |
|----|------|
| **R8** | **Do not merge-authorize H1+H2.** Drop “merge H1+H2” as default path. Next human auth = **H1 only**. H1 deliverables **exclude** full approve→execute Skill path (may add approve route stub that enqueues resume **only if** H2 lands immediately after — prefer **defer approve route to H2** to avoid half-API; **reject/cancel in H1**). |

**Recommended H1 charter (tight):**

1. Migration `require_sql_approval` (+ recommended `approval_requested_at`)  
2. `ACTIVE_STATUSES` + `hitl_rejected`  
3. Kill-switch config  
4. Plan→`awaiting_approval` (no plane)  
5. Reject + cancel-from-wait (API CAS)  
6. Wait-timeout sweeper (R1)  
7. In-flight includes wait (R5)  
8. H1 smokes (R7)  
9. Create flag + TaskOut field  

**Explicitly H2:** approve route + Worker execute phase + snapshot + `platform.hitl` complete + full Gate suite.

---

## 2. Condition locks summary (SSOT amendments)

| ID | Lock statement |
|----|----------------|
| R1 | Wait timeout via **`expire_awaiting_approval` sweeper**, not Skill thread |
| R2 | `plan`/`execute` are phase fields only, not DB statuses |
| R3 | API may terminalize reject/cancel-from-wait; approve must not execute in-request |
| R4 | TaskOut exposes flag; cancel UX includes wait (H1 API / H3 FE) |
| R5 | In-flight = `running` ∪ `awaiting_approval` |
| R6 | Dedicated resume CAS; execute body in H2 |
| R7 | Split smoke/Gate exits by Sprint |
| R8 | Next auth = **H1 only**; no H1+H2 merge |

---

## 3. Version posture (reconfirmed)

- Default ship line: **v1.2.x MVP** if scope held.  
- Escalate to **v2.0.0** evaluation only on plan §A4.4 triggers.  
- **No** `v2.0.0` tag now.

---

## 4. Explicit non-actions (this review)

| Action | Status |
|--------|--------|
| Coding | **Not run** |
| Commit / push | **Not run** |
| Authorize H1 coding | **Not granted** — awaiting operator acceptance of locks + separate H1 auth |
| Authorize H2 | **Not granted** |
| Tag | **Not run** |

---

## 5. Next human gate

1. Accept this Review (**PASS WITH CONDITIONS**) and R1–R8 locks (mirrored on plan Addendum).  
2. Separately authorize **H1 Implementation Sprint** only.  
3. After H1 Implementation Review PASS → apply for **H2**.

---

**End of HITL Implementation Plan Review.**
