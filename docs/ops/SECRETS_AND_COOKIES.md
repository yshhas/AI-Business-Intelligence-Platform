# Secrets and Cookies

**Status:** Wave 2 decision record

## Secret management

| Secret | Where | Guidance |
|--------|-------|----------|
| `JWT_SECRET` | API env | Random ≥32 chars in production/staging; never commit |
| `LLM_API_KEY` | Worker env | Provider key; rotate via env / secret store |
| `POSTGRES_*` / `DATABASE_URL` | Compose / env | Use `.env` locally; SOPS or cloud secret manager in prod |
| `POSTGRES_RO_DSN` | Worker env | RO credentials; separate from platform DB |

### Local development

Copy [`.env.example`](../../.env.example) to `.env` at repo root. Never commit `.env`.

### Production / staging

- Prefer **SOPS**-encrypted files or your cloud secret manager (AWS SM, GCP SM, Vault).
- Inject at deploy time; do not bake secrets into images.
- Compose `env_file: ../.env` is for local/dev only.

## Auth token storage (Wave 2)

**Decision:** keep **localStorage + refresh token** flow for Wave 2.

| Approach | Wave 2 | Rationale |
|----------|--------|-----------|
| localStorage access + refresh | **Yes** | Already implemented; SPA-friendly |
| HttpOnly secure cookies | **Deferred** | Requires CSRF strategy + same-site cookie design |

The frontend stores `access_token` and `refresh_token` in localStorage (`authStore`).
Refresh uses `POST /api/v1/auth/refresh`. HttpOnly cookies may be adopted in a later
trust-hardening wave with explicit CSRF and cookie domain policy.

## CORS

When serving UI via nginx on `:8080`, add `http://localhost:8080` to `CORS_ORIGINS`
if the browser calls the API directly (not via nginx same-origin proxy).

See [OPS_CONFIG_MATRIX.md](OPS_CONFIG_MATRIX.md) for variable reference.
