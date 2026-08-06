# HITL H2 Design / Implementation Review

**Document type:** Design + pre-implementation Review (**Design-only · no coding**)  
**Date:** 2026-07-22  
**Baseline:** H1 commit `bb0cf0c` · tag `v1.1.0` still tip of released line; `main` ahead 1 locally  
**SSOT:** `docs/HITL_IMPLEMENTATION_PLAN.md` (R1–R8 + H2 charter)  
**Prior:** H1 Implementation Review **PASS** · H1 commit authorized and done  

**Constraints:**

- No coding · no commit · no push · no tag · no release  
- H2 implementation **not authorized** by this document  
- No FE (H3) · no v2.0.0  

**Spine (unchanged):**

```text
Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts
```

---

## 0. Verdict

| Focus | Design readiness |
|-------|------------------|
| Approve → Execute / Resume lifecycle | **Ready** (locks below) |
| CAS / concurrency | **Ready** (mandatory CAS matrix) |
| Worker Resume flow | **Ready** |
| Timeout / Reject / Cancel races | **Ready** (precedence table) |
| Smoke / Gate / Eval coverage | **Ready** (H2 suite defined) |

**Overall:** **PASS — ready to authorize H2 Implementation Sprint** after operator acceptance of locks **H2-L1…H2-L12**.

**Version posture:** Remains **v1.2.x MVP** candidate if H2 stays inside SSOT (opt-in pause + Worker resume). No `v2.0.0` tag.

---

## 1. H1 baseline (what H2 builds on)

| Capability | H1 state |
|------------|----------|
| Plan → `awaiting_approval` | Done (agent `hitl_plan_only` + mock plan) |
| Reject / cancel-from-wait | Done (API CAS) |
| Wait timeout sweeper | Done (`expire_awaiting_approval`) |
| In-flight includes wait | Done |
| Kill-switch | Done (default off) |
| SQL snapshot at park | `platform.hitl.sql_sha256` (+ `sql` in result_json) |
| Approve / execute resume | **Absent** (by design) |

**H2 must not reopen:** Policy Gate algorithms · Skill terminal writes · FE scope · mandatory HITL · approve-with-edit.

---

## 2. Approve → Execute / Resume lifecycle

### 2.1 Target sequence

```text
awaiting_approval
  → POST .../approve   (creator/owner; kill-switch on)
  → API: validate status + kill-switch; DO NOT execute SQL in-request (R3)
  → enqueue resume signal (same task_id)  OR  mark resume_requested + enqueue
  → Worker: CAS awaiting_approval → running (phase=execute)
  → bind execute_select; hitl_plan_only=False
  → verify SQL snapshot (L10); mismatch → failed (fail-closed)
  → Skill execute_sql (+ summarize/charts/report) with Gate at tool/plane
  → succeeded | failed (existing classes)
  → seal Trace / Artifacts / slim (existing)
```

### 2.2 Phase model (R2)

| Stored `status` | `platform.hitl.phase` | Meaning |
|-----------------|----------------------|---------|
| `awaiting_approval` | `awaiting` | Human wait (H1) |
| `running` | `execute` | Post-approve execute |
| terminals | `rejected` / `cancelled` / `timed_out` / … | As today |

Do **not** invent DB statuses `running_exec` / `approved`.

### 2.3 Skill / Kernel

| Mode | Behavior |
|------|----------|
| Plan (H1) | Stop after Gate allow; `execute_select` forbidden |
| Execute (H2) | Start from approved SQL (or resume graph from execute); **must not** regenerate different SQL silently |

**Recommended execute entry (H2-L1):**  
Worker passes `hitl_execute_only=True` + `approved_sql` into runtime hints. Skill/graph **skips** generate/validate **or** re-validates Gate on `approved_sql` then executes — **must not** call LLM to invent new SQL. Prefer: load snapshot SQL → Gate validate → execute → downstream.

Mock path: if `require_sql_approval` and status became `running` via resume, run execute fiction from stored SQL (or short mock execute) — enough for smoke without LLM.

### 2.4 API surface (H2)

| Method | Path | Effect |
|--------|------|--------|
| POST | `.../tasks/{id}/approve` | Only from `awaiting_approval`; enqueue Worker resume; return TaskOut (still awaiting **or** already `running` if Worker won race — see §4) |

**Errors (align with H1 reject):**

| Condition | Code |
|-----------|------|
| Kill-switch off | **409** |
| Wrong status (not awaiting) | **409** |
| Not creator/owner | **403** |
| Not found | **404** |
| Double approve after terminal | **409** |

**Permission:** Reuse cancel bar (creator/owner) — same as reject (H2-L2).

---

## 3. CAS & concurrency safety

### 3.1 Mandatory CAS transitions (H2-L3)

| Transition | CAS predicate | Winner |
|------------|---------------|--------|
| Park (H1) | `running` → `awaiting_approval` | Already H1 (tighten if needed) |
| Approve resume | `status==awaiting_approval` → `running` (+ clear cancel if any) | Worker (preferred) **or** API then Worker no-ops |
| Reject | `awaiting_approval` → `failed`/`hitl_rejected` | API (H1) |
| Cancel-from-wait | `awaiting_approval` → `cancelled` | API (H1) |
| Wait timeout | `awaiting_approval` → `timed_out` | Sweeper (H1) |
| Execute success/fail | `running` → terminal | Worker (existing) |

All writers use **rowcount-checked UPDATE … WHERE status=…** (or equivalent). If `rowcount==0`, treat as lost race → **no** side effects (no second execute, no overwrite terminal).

### 3.2 Who flips `awaiting → running`? (H2-L4)

**Preferred:** API only enqueues `task_id` (resume); **Worker** performs CAS to `running` at start of execute phase.  
**Rejected:** API thread runs Skill/Plane.

**Acceptable variant:** API CAS to `running` + `platform.hitl.phase=execute` + enqueue; Worker refuses if not `running` with HITL execute marker. Prefer Preferred to keep fence ownership with Worker.

### 3.3 Double-approve / approve-after-reject

| Race | Expected |
|------|----------|
| Two approves | First enqueues; second **409** (status no longer awaiting) |
| Approve after reject/cancel/timeout | **409** |
| Reject after approve CAS to running | Reject **409**; cancel becomes cooperative cancel on `running` (P1.1) |

### 3.4 Idempotent resume dequeue (H2-L5)

If Redis delivers resume twice: Worker CAS `awaiting→running` succeeds once; second claim/resume sees `running` or terminal → **skip** (no double execute).  
If Preferred model (API does not CAS): Worker must distinguish **first plan claim** (`pending→running` plan) vs **resume** (`awaiting→running` execute). Use explicit resume queue key **or** payload flag / DB column `hitl_resume_requested` (bool) set by approve API under CAS-friendly update.

**Recommended (H2-L6):** Add nullable/boolean `hitl_resume_requested` (migration) set `true` only when `status=awaiting_approval` via CAS update in approve API; Worker loop (or `process_task` entry) selects tasks with `awaiting_approval AND hitl_resume_requested` **or** processes resume enqueue that only succeeds CAS when awaiting. Clear flag when entering execute or on terminal.

Minimal alternative without new column: dedicated Redis list `aibi:hitl_resume` of task_ids; Worker BRPOP resume list in addition to main queue (H2-L6b). Prefer **one** of L6 / L6b at impl — do not implement both.

---

## 4. Worker Resume flow (detailed)

```text
1. Receive resume (queue or flag)
2. Load task; if terminal → skip
3. CAS: UPDATE … SET status='running', hitl_resume_requested=false,
         last_heartbeat_at=now()
       WHERE id=? AND status='awaiting_approval'
   if rowcount=0 → skip (lost to reject/cancel/timeout)
4. Set platform.hitl.phase='execute'; decision='approved' (actor optional)
5. Open write fence via status=running (existing write_allowed)
6. Snapshot check: sha256(result_json.sql) == platform.hitl.sql_sha256
   mismatch → failed (skill_error or dedicated hitl_snapshot_mismatch — prefer
   failure_class=skill_error + clear error_message for MVP, or add
   hitl_snapshot_mismatch in H2 — H2-L7: use skill_error + explicit message)
7. Run execute-only Skill/mock
8. Existing success/fail/cancel/timeout paths
9. Do NOT re-enter awaiting_approval after execute
```

**In-flight:** Task remains counted (was awaiting, now running) — capacity unchanged at approve time (H2-L8).

**Stale reclaim:** Execute `running` uses existing heartbeat/reclaim; wait still excluded (H1 L6).

**Memory write:** Allowed only after successful execute (not plan) — already true in H1 agent_runtime.

---

## 5. Timeout · Reject · Cancel races

### 5.1 Precedence while `awaiting_approval` (H2-L9)

| Event A | Event B | Winner | Loser effect |
|---------|---------|--------|--------------|
| Sweeper timeout | Approve | First CAS wins | Approve → 409 or no-op enqueue ignored |
| Reject | Approve | First CAS wins | Other → 409 |
| Cancel-from-wait | Approve | First CAS wins | Other → 409 |
| Approve CAS→running | Cancel | Cancel becomes **cooperative** on running (P1.1) | Execute may partial; fence applies |
| Approve→running | Sweeper | Sweeper only matches awaiting → **no-op** | Execute continues under wall-clock |

**Invariant:** After leaving `awaiting_approval`, sweeper **must not** terminalize the Run as wait-timeout.

### 5.2 Approve API vs in-flight sweeper

Approve handler must re-read status after enqueue or rely solely on Worker CAS (Preferred). Never assume enqueue implies execute will run.

### 5.3 Kill-switch mid-flight (H2-L10)

If kill-switch flips off while awaiting: reject/approve → **409**; parked Runs still cancel/timeout. Already parked rows keep `require_sql_approval=true` but new approves denied — document in ops. Do not auto-execute on kill-switch off.

---

## 6. Smoke / Release Gate / Eval (H2 coverage)

### 6.1 New / extended smokes (`smoke_hitl_h2` or extend suite)

| Case | Assert |
|------|--------|
| Approve → execute → succeeded (or governed fail) | Plane allowed only after approve; status terminal success/fail |
| Snapshot mismatch | Fail-closed; no plane with foreign SQL |
| Double approve | Second **409** |
| Approve after reject | **409** |
| Reject/cancel/timeout vs approve race | At most one winner; no execute after reject/cancel/timeout |
| Kill-switch off approve | **409** |
| Resume idempotency | Dual resume enqueue → single execute |

Seed style: prefer **direct pending + process_task** (H1 lesson) plus **controlled resume enqueue** without racing unrelated live workers when possible.

### 6.2 Release Gate

- Keep `smoke_hitl_h1`  
- Add `smoke_hitl_h2` (or merge into one `smoke_hitl_sql_approval` with H1+H2 sections)  
- Gate red ⇒ no H2 merge  

### 6.3 Eval

- Remain **flagless** (no HITL create flag)  
- core / quality / profile must stay **EVAL_OK**  
- No new Eval suite required for H2 MVP  

### 6.4 Optional (P2, not blocking H2 exit)

- Agent-path Gate deny never awaits (design already)  
- Assert production defaults in separate smoke  

---

## 7. H2 charter (authoritative when coding authorized)

1. `POST .../approve` + permission + kill-switch + 409 matrix  
2. Resume mechanism (**H2-L6 or L6b** — pick one in impl)  
3. Worker CAS `awaiting→running` + execute phase  
4. Execute-only Skill/mock path (no silent SQL regen)  
5. Snapshot check fail-closed (**H2-L7**)  
6. Race handling per §5  
7. Trace `platform.hitl` update (`decision=approved`, `phase=execute`)  
8. `smoke_hitl_h2` + Gate wiring  
9. H2 Implementation Report + Review  

**Out of H2:** FE (H3) · approve-with-edit · mandatory policy · Semantic/Multi-Agent · Cookie · push/tag  

---

## 8. Locks summary (accept before H2 coding)

| ID | Lock |
|----|------|
| **H2-L1** | Execute uses approved SQL; no LLM regen of different SQL |
| **H2-L2** | Approve auth = creator/owner (same as cancel/reject) |
| **H2-L3** | All status flips CAS with rowcount check |
| **H2-L4** | Skill/Plane execute only on Worker after resume — never in API request |
| **H2-L5** | Dual resume → single execute |
| **H2-L6 / L6b** | Pick resume signal: DB flag **or** dedicated Redis list (not both) |
| **H2-L7** | Snapshot mismatch → failed, fail-closed |
| **H2-L8** | Approve does not change in-flight accounting unexpectedly |
| **H2-L9** | Wait-timeout sweeper never wins after leave-awaiting |
| **H2-L10** | Kill-switch off blocks approve; no auto-execute |
| **H2-L11** | No FE in H2 |
| **H2-L12** | No `v2.0.0` tag; stay v1.2.x candidate |

---

## 9. Risks

| Risk | Level | Mitigation |
|------|-------|------------|
| Double execute | High | CAS + idempotent resume (L3/L5) |
| Execute after reject/timeout | High | CAS predicate awaiting only |
| API-thread execute | High | L4 forbidden |
| SQL drift | Med | L1 + L7 |
| Live Worker race in smokes | Med | Seed pattern from H1 |
| Capacity confusion | Low | L8 |

---

## 10. Operator acceptance

| # | Ask |
|---|-----|
| **B1** | Accept H2 lifecycle §2 |
| **B2** | Accept CAS / race matrix §3–§5 |
| **B3** | Accept resume choice deferred to impl as **L6 or L6b** (one only) |
| **B4** | Accept smoke/Gate/Eval plan §6 |
| **B5** | H2 coding only after **separate** explicit authorization |

---

## 11. Explicit non-actions (now)

| Action | Status |
|--------|--------|
| Coding H2 | **Not authorized** |
| Commit / push | **Not run** |
| Tag / release | **Not run** |
| H3 FE | **Deferred** |

---

## 12. References

- `docs/HITL_IMPLEMENTATION_PLAN.md`  
- `docs/HITL_IMPLEMENTATION_PLAN_REVIEW.md`  
- `docs/HITL_H1_IMPLEMENTATION_REPORT.md` / `REVIEW.md`  
- H1 commit `bb0cf0c`  
- `backend/app/workers/analysis_worker.py` · `write_fence.py` · `task_service.py` · `runtime_essentials.py`

---

**End of HITL H2 Design / Implementation Review.**  

Awaiting **B1–B5**. On acceptance + separate H2 auth → implement charter §7 only.
