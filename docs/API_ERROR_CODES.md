# API Error Code Matrix

**Status:** Wave 3 + Stabilization  
**Scope:** Product Shell HTTP contracts used by the React workbench and smokes.

## Conventions

| Field | Meaning |
|-------|---------|
| HTTP status | Transport / client branching |
| `detail` | Human-readable string (FastAPI default) |
| `failure_class` | On `AnalysisTask` when a Run/enqueue fails with an audit row |
| `X-Request-ID` | Correlation (also on error responses when middleware ran) |
| `Idempotency-Key` | Optional header on task create — Redis 24h replay |

Clients should branch on **HTTP status** first, then parse `detail` / task `failure_class` for UX copy.

---

## Auth — `/api/v1/auth`

| Status | When | Typical `detail` | Client action |
|--------|------|------------------|---------------|
| 201 | Register ok | — | Store `access_token` + `refresh_token` |
| 200 | Login / refresh / OIDC callback ok | — | Store tokens |
| 204 | Logout ok (refresh jti revoked) | — | Clear local tokens |
| 400 | Validation / bad OIDC state | Pydantic / `Invalid or expired OIDC state` | Show field error |
| 401 | Bad credentials / bad-expired / **revoked** refresh | `Incorrect email or password` / `Invalid or expired refresh token` | Re-login; refresh once on API 401 |
| 404 | OIDC disabled | `OIDC not enabled` | Hide SSO UI |
| 409 | Email taken | `Email already registered` | Suggest login |
| 429 | Rate limit | `Rate limit exceeded: ...` | Back off |
| 503 | OIDC Redis state / hardened rate-limit Redis down | | Retry later |

### Tokens

| Token | `type` claim | Default TTL | Use |
|-------|--------------|-------------|-----|
| Access | `access` | `ACCESS_TOKEN_EXPIRE_MINUTES` (30) | `Authorization: Bearer` (stateless) |
| Refresh | `refresh` | `REFRESH_TOKEN_EXPIRE_MINUTES` (10080) | `POST /api/v1/auth/refresh`; **`jti` stored** in `refresh_sessions` |

### Refresh sessions (P1.2)

| Behavior | Rule |
|----------|------|
| Multi-device | Multiple live refresh `jti` rows per user allowed |
| Rotation | Successful refresh **revokes** previous `jti`; reuse → **401** (no family kill-switch in Sprint 2) |
| Logout | `POST /api/v1/auth/logout` with `{refresh_token}` revokes **that** session only (204 even if already dead) |
| Deploy note | Refresh tokens issued before migration have no row → refresh **401**; users must re-login |

### OIDC (optional)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/oidc/login` | `{authorize_url, state}` — state stored in Redis |
| POST | `/oidc/callback` | body `{code, state}` → JWT pair |

---

## Workspaces / Datasets

| Status | When | Notes |
|--------|------|-------|
| 401 | Missing/invalid access token | |
| 403 | Skill disabled / forbidden action / ACL | |
| 404 | Workspace/dataset hidden or missing | Non-members get 404 |
| 409 | Dataset not ready | |
| 413 | Upload too large | `MAX_UPLOAD_BYTES` |

Bind planes: `POST .../datasets/upload` · `.../postgres-ro` · `.../mysql-ro` (DSN from env only).

---

## Tasks — `/api/v1/workspaces/{id}/tasks`

| Status | `failure_class` (task row) | When |
|--------|----------------------------|------|
| 201 | — | Enqueued `pending` (or idempotent replay of same task) |
| 400 | — | Empty question / bad body / bad OIDC-style validation |
| 401/404 | — | Auth / membership |
| 403 | — | Skill disabled / unknown skill / ACL |
| 409 | — | Dataset not ready; cancel on terminal; idempotency in-progress |
| 429 | `budget_rejected` | Soft LLM token budget (UTC day) |
| 429 | `capacity_rejected` | Queue depth or global in-flight cap |
| 429 | — | API rate limit on create |
| 503 | `enqueue_error` | Redis LPUSH failed after task insert |
| 503 | — | Idempotency store unavailable (hardened env) |

### Create body

| Field | Notes |
|-------|-------|
| `dataset_id` | Required |
| `question` | Required |
| `skill_id` | Optional; default `data.bi`; also `data.profile` |

Header: `Idempotency-Key` (optional).

### Terminal task statuses

`succeeded` · `failed` · `cancelled` · `timed_out`

### Common `failure_class` values

| Value | Meaning |
|-------|---------|
| `budget_rejected` | Soft cost budget |
| `capacity_rejected` | Runtime capacity |
| `enqueue_error` | Queue push failed |
| `policy_denied` | SQL Gate / Policy |
| `connector_error` | Data plane |
| `skill_error` | Skill / LLM pipeline |
| `timeout` | Wall-clock |
| `cancelled` | User cancel |
| `runtime_reclaimed` | Stale running reclaim |
| `internal_error` | Unexpected |
| `unknown` | Unclassified |

---

## MCP — `/api/v1/workspaces/{id}/mcp`

| Status | When |
|--------|------|
| 200 | `GET /tools` · `POST /invoke` ok |
| 400 | Missing `dataset_id` / bad args |
| 403/404 | ACL / dataset missing / unknown tool |

Tools always use **ACL-projected** allowlists (`dataset_id` required). SQL tool never executes — Gate validate only.

---

## Related

[OIDC.md](./OIDC.md) · [MCP.md](./MCP.md) · [DATA_PLANE.md](./DATA_PLANE.md) · [OPS_RUNBOOK.md](./OPS_RUNBOOK.md)
