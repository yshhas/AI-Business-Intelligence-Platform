# Sprint 2 Implementation Review Report

**Review date:** 2026-07-22  
**Base commit:** `0ce9204` (Sprint 1) · Sprint 2 changes **uncommitted**  
**Scope reviewed:** P1.2 · P1.5 · P1.3  
**Verdict:** **PASS** — suitable for commit after your authorization  

**Not performed:** commit · push · release

---

## Executive verdict

| Area | Result | Blocking? |
|------|--------|-----------|
| P1.2 Refresh revoke | Aligns with approved MVP | No |
| P1.5 list_tasks batch ACL | Semantics preserved; no bypass found | No |
| P1.3 Memory TTL/cap | Cap enforceable; grandfather OK | No |
| Spine | Unchanged | No |
| Release Gate / Eval | Reported green; no hidden Gate holes found in code path | No |

**P0 findings:** none  
**P1 findings:** none blocking  
**P2 residual notes:** concurrent refresh race (session fan-out); unused `oidc_service.issue_auth_tokens`; deny-path list ACL smoke not added

---

## 1. P1.2 Refresh revoke

### 1.1 Migration safety — **PASS**

`0014_sprint2_refresh_memory`:

- Additive only: new `refresh_sessions` table; nullable `workspace_column_memory.expires_at`.
- FK `user_id → users.id` CASCADE; unique `jti`.
- No destructive rewrite of `users` / existing JWT rows.
- Deploy effect (documented): pre-migration refresh tokens lack rows → refresh **401** → re-login. Acceptable for this stage.

### 1.2 Rotation truly revokes old jti — **PASS**

`rotate_refresh`:

1. `get_active_session(old_jti)`  
2. `issue_token_pair` (new row)  
3. `revoke_session(old, replaced_by_jti=new_jti)`  
4. Route `db.commit()` atomic  

Reuse path: `get_active_session` fails when `revoked_at` set → `RefreshSessionError` → HTTP **401**.

### 1.3 Reuse → 401 stable — **PASS**

Covered by `smoke_auth_refresh` (`REFRESH_ROTATION_REUSE_401_OK`). Unknown/missing jti also 401. No family kill-switch (as approved).

### 1.4 Logout = current session only — **PASS**

`logout` → `revoke_jti` for body refresh only. Smoke: logout A, device B still refreshes (`MULTI_DEVICE_SESSION_OK` / `LOGOUT_CURRENT_SESSION_OK`).

### 1.5 Access token stays stateless — **PASS**

`get_current_user` uses `decode_access_token` only; no access `jti` store. Logout does not blacklist access (short TTL by design).

### 1.6 OIDC / register / login unified — **PASS** (with note)

All three HTTP success paths use `_auth_response` → `rs.issue_token_pair` + commit.

| Path | Session lifecycle |
|------|-------------------|
| register / login / oidc callback | **Yes** via `_auth_response` |
| refresh | **Yes** via `rotate_refresh` |
| `oidc_service.issue_auth_tokens` | **Unused** by routes; still mints without DB — **P2 hygiene**, not a live hole |

---

## 2. P1.5 list_tasks

### 2.1 ACL semantics — **PASS**

Batched logic mirrors `can_access_task` / `can_read_dataset`:

| Rule | Behavior |
|------|----------|
| Workspace owner | Always visible |
| Task creator (`task.user_id == uid`) | Always visible |
| Dataset with **no** ACL rows | Default-open → visible |
| Dataset with ACL | Visible iff caller ACL `can_read` |
| Missing dataset | Skipped (same as before) |

### 2.2 Owner / creator / reader — **PASS** (no regression found)

Owner short-circuit skips ACL (same as `is_workspace_owner` early return). Creator bypass preserved. Reader uses preloaded entry `can_read` only (not `can_run`) — correct for list/read.

### 2.3 No permission bypass from fewer queries — **PASS**

Optimization is preload + in-memory decide; filters still applied **after** membership (`require_workspace_member` + `RUN_LIST`). Restricted datasets without caller ACL entry remain hidden.

Residual: list still applies SQL `limit` **before** visibility filter (pre-existing; may return &lt; limit). Not introduced by P1.5.

### 2.4 API contract — **PASS**

`routes_tasks.list_tasks` signature, query aliases, `TaskListOut` unchanged. No pagination change.

---

## 3. P1.3 Memory TTL / cap

### 3.1 TTL vs existing linking — **PASS**

`load_synonyms` keeps rows where `expires_at IS NULL OR expires_at > now`.  
Grandfather NULL rows remain available for linking until upsert refreshes TTL — matches decision.  
Eval core/quality/profile reported **EVAL_OK** (no linking regression signal).

### 3.2 Grandfather NULL — **PASS**

Migration adds nullable column without backfill. Upsert sets `expires_at` when TTL_DAYS &gt; 0.

### 3.3 Cap eviction workspace-isolated — **PASS**

All prune/count/delete predicates include `workspace_id == …`. No cross-tenant delete path.

### 3.4 `protect_phrases` vs capacity runaway — **PASS** (bounded)

- Pre-upsert prune may under-evict when many phrases are protected (≤16 per write).  
- **Post-upsert** `prune(..., room_for=0)` runs **without** protect → enforces `count ≤ max_rows`.  
- Smoke: `WORKSPACE_MEMORY_CAP_OK`.  
- Transient overshoot only inside the same DB transaction before final prune — not durable.

Note: protect matches on `phrase` alone (not dataset). May over-protect same phrase on another dataset in the **same** workspace; final prune still caps. Acceptable MVP.

### 3.5 Prune vs write_fence — **PASS**

`agent_runtime` calls `remember_from_link` only when `write_allowed(...)`. Prune is internal to remember; abort/fence deny → no memory write/prune. Kernel/Skill unchanged.

---

## 4. Spine impact — **PASS**

| Layer | Sprint 2 touch? |
|-------|-----------------|
| Product Shell | Auth + list_tasks + memory service/docs |
| Worker | Unchanged orchestration; still fences memory write |
| Kernel | No |
| Skill | No |
| Policy | No |
| Data Plane | No |
| Trace / Artifacts | No |

Direction preserved: **Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts**.

---

## 5. Release Gate — **PASS** (no hidden blockers found)

| Check | Assessment |
|-------|------------|
| Migration | Gate runs `alembic upgrade head` → includes `0014` |
| Auth smoke | Extended revoke/rotation/multi-device |
| Memory smoke | TTL + cap in wave3 |
| list_tasks | `smoke_list_tasks_nplus1` wired |
| OpenAPI | `/logout` required |
| Eval c/q/p | Reported EVAL_OK |
| Full Gate | Reported RELEASE GATE PASS |

No Gate path skips `0014` or auth revoke coverage. Residual test gap (P2): explicit **deny** list visibility case (viewer without `can_read`) not added — logic review covers it; smoke does not.

---

## 6. Risk rating & commit standard

| | |
|--|--|
| **Commit standard** | **Met** |
| **P0** | None |
| **P1** | None |
| **P2** | Concurrent double-refresh fan-out; dead `issue_auth_tokens`; optional deny-path list smoke; family reuse detection (deferred by design) |

**Recommendation:** Approve Implementation Review → authorize commit when ready.  
Suggested message (unchanged recommendation):

```text
fix(auth,runtime): refresh jti revoke, memory TTL/cap, list_tasks batch
```

---

## 7. Pause

Review **PASS**. Awaiting your commit authorization.  
**Still forbidden until you say so:** `git commit` · `git push` · release/tag.
