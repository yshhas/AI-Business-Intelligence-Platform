# Phase 1 checklist

## Backend

- [x] Step 1.1 models + Alembic `0001_phase1_auth` (`users` / `workspaces` / `workspace_members`)
- [x] Step 1.2 bcrypt hash/verify + PyJWT create/decode
- [x] Step 1.3 `POST /api/v1/auth/register` (user + default workspace + owner + JWT)
- [x] Step 1.4 `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
- [x] Step 1.5 `GET/PATCH /api/v1/workspaces`
- [x] Step 1.1b DB dialect abstraction (`db_dialect.py`) — SQLite now, Postgres later via `DATABASE_URL` only

## Frontend

- [x] Step 1.6 register / login pages
- [x] token save (`localStorage`) + logout clear
- [x] `RequireAuth` guard
- [x] post-login **Dashboard** (`/app`)

## Verified

- [x] Register creates user + workspace + owner member + JWT
- [x] `/me` with Bearer works
- [x] Workspace list + rename
- [x] Bad password → 401; duplicate email → 409
- [x] Bad/missing token → 401; cross-workspace → 404
- [x] Frontend build / Dashboard landing
- [x] Session persistence via localStorage (refresh-safe)
- [x] **Final acceptance** — see `PHASE1_ACCEPTANCE.md`

## Database policy (Phase 1 final)

- [x] Runtime metadata DB = **PostgreSQL** (Compose `aibi-postgres`, host `:5433`)
- [x] Dialect abstraction retained (`db_dialect.py`); no SQLite business coupling
- [x] SQLite file kept only as historical smoke artifact
- [x] Switch record: `docs/PHASE1_POSTGRES_SWITCH.md`

## Out of scope (stop line)

- [ ] Dataset / DuckDB — Phase 2
- [ ] Redis / task queue — Phase 3
- [ ] Agent / LangGraph — Phase 4–5
