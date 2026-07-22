# Sprint 2 Implementation Report

**Status:** Implemented · smokes + Release Gate **PASS** · **not committed**  
**Base:** `0ce9204` (Sprint 1)  
**Scope:** P1.2 Refresh revoke/rotation · P1.5 `list_tasks` N+1 · P1.3 Memory TTL/cap  

Spine unchanged: Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts.

---

## 1. Decisions locked (as authorized)

| Item | Decision |
|------|----------|
| P1.2 sessions | Multi-device; logout = current refresh `jti` only; no device UI |
| P1.2 reuse | Old `jti` invalid after rotate → **401**; no family kill-switch (follow-up) |
| P1.3 | TTL **90d**, cap **2000**/workspace, `expires_at=NULL` grandfather, expire→LRU |
| P1.5 | Batch preload + in-memory ACL; **no** API/pagination change |

---

## 2. P1.2 Refresh revoke / rotation

### Delivered

| Piece | Location |
|-------|----------|
| Table `refresh_sessions` | migration `0014_sprint2_refresh_memory` |
| Model | `backend/app/models/refresh_session.py` |
| Service | `backend/app/services/refresh_sessions.py` |
| Login/register/OIDC | persist `jti` via `issue_token_pair` |
| `POST /refresh` | `rotate_refresh` (revoke old, mint new) |
| `POST /logout` | revoke current `jti`; **204** idempotent |
| FE | `auth.logout` + `AppLayout` best-effort revoke then `clearSession` |
| Docs | `API_ERROR_CODES.md` |

### Semantics

- Access tokens remain **stateless**.
- Pre-migration refresh tokens have no row → refresh **401** (re-login).
- Follow-up (not done): refresh-family reuse detection / logout-all.

### Tests

`smoke_auth_refresh`: rotation reuse 401 · logout current · multi-device other session still rotates · OpenAPI includes `/logout`.

---

## 3. P1.5 `list_tasks` N+1

### Delivered

`task_service.list_tasks` now:

1. One task query (unchanged filters/limit/order)  
2. Batch `Dataset IN (...)`  
3. One ACL `GROUP BY` for restricted datasets  
4. One ACL entry preload for the caller  
5. In-memory visibility (owner / creator / default-open / `can_read`)

### Contract

Unchanged: query params, `TaskListOut`, permission outcomes.

### Tests

`smoke_list_tasks_nplus1`: 25 tasks + restricted ACL → **query count 4** (≤8 gate) · wired into Release Gate.

---

## 4. P1.3 Memory TTL + capacity

### Delivered

| Piece | Detail |
|-------|--------|
| Column `expires_at` | nullable; grandfather NULL |
| Config | `WORKSPACE_MEMORY_TTL_DAYS=90`, `WORKSPACE_MEMORY_MAX_ROWS=2000` |
| Write path | expire delete → LRU (skip `protect_phrases`) → upsert → post-cap prune |
| Read path | `load_synonyms` filters expired |
| Docs | `WORKSPACE_MEMORY.md`, `OPS_CONFIG_MATRIX.md`, `.env.example` |

### Cap fix during verification

Pre-upsert LRU could evict phrases about to be upserted, then re-insert and exceed cap. Fixed with `protect_phrases` + post-upsert `prune(..., room_for=0)`.

### Tests

`smoke_wave3_platform`: `WORKSPACE_MEMORY_TTL_OK` · `WORKSPACE_MEMORY_CAP_OK`.

---

## 5. Migration

**`0014_sprint2_refresh_memory`** (revises `0013_wave3_memory_acl_tables`):

- create `refresh_sessions` + indexes  
- add `workspace_column_memory.expires_at` + indexes  

---

## 6. Verification

| Check | Result |
|-------|--------|
| `alembic upgrade head` | **PASS** → `0014` |
| `smoke_auth_refresh` | **PASS** |
| `smoke_list_tasks_nplus1` | **PASS** (queries=4) |
| `smoke_wave3_platform` | **PASS** |
| `smoke_openapi_contract` | **PASS** |
| `smoke_release_gate` | **PASS** |
| Eval core / quality / profile | **EVAL_OK** |

---

## 7. Out of scope (confirmed untouched)

P1.4 · P1.7 · P1.8 Cookie · P1.10 · HITL · Semantic Layer · Multi-Agent · IaC / K8s · Kernel/Policy/Data Plane contracts · Spine

---

## 8. Follow-ups (not Sprint 2)

1. Refresh **family** reuse → revoke-all for that user  
2. Optional `POST /logout-all`  
3. Periodic memory expire job (lazy prune is enough for MVP)  
4. `oidc_service.issue_auth_tokens` still mints without DB session (unused by routes; routes use `_auth_response`)

---

## 9. Commit readiness

| | |
|--|--|
| Implementation | Complete vs approved design |
| Gate | Green |
| Commit / push / release | **Not done** — awaiting Implementation Review + commit auth |

Suggested commit message (when authorized):

```text
fix(auth,runtime): refresh jti revoke, memory TTL/cap, list_tasks batch
```
