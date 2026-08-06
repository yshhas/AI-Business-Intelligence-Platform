# Ops — Operator Runbook

**Status:** Era 3 Deployment Hygiene + T-12 Dockerized API/Worker  
**Companion:** [OPS_CONFIG_MATRIX.md](./OPS_CONFIG_MATRIX.md) · [docker/README.md](../docker/README.md)

## Pinned dependencies (reproducibility)

| Component | Pin |
|-----------|-----|
| Platform Postgres | `postgres:16-alpine` (Compose) · host **5433** |
| Redis | `redis:7-alpine` · host **6379** |
| RO data plane | `postgres:16-alpine` as `postgres_ro` · host **5434** |
| App / Worker | Image `aibi-app:local` (`docker/Dockerfile`) · ports **8000** |
| Schema | `alembic upgrade head` (API entrypoint on start) |

## Path A — Full Compose (T-12)

```powershell
copy .env.example .env   # first time; set JWT_SECRET / optional LLM_API_KEY
docker compose -f docker/docker-compose.yml --env-file .env up -d --build
```

Brings up: **postgres · redis · postgres_ro · api · worker**.  
Compose **overrides** `DATABASE_URL` / `REDIS_URL` / `POSTGRES_RO_DSN` inside api/worker to service DNS (`postgres`, `redis`, `postgres_ro`). Host-port URLs in `.env` remain for Path B (venv).

Probes:

| Probe | URL |
|-------|-----|
| Liveness | `GET http://127.0.0.1:8000/health/live` |
| Readiness | `GET http://127.0.0.1:8000/health/ready` (DB + Redis) |

Worker has no HTTP health; it starts after API is healthy. Check `docker logs aibi-worker`.

**Port conflict:** If a host `uvicorn` already binds `127.0.0.1:8000`, browser/`curl` may hit the old process (Compose still healthy inside the container). Stop the host API before Path A, or verify with:

```powershell
docker exec aibi-api curl -fsS http://127.0.0.1:8000/health/ready
```

Frontend (optional, still on host):

```powershell
cd frontend
npm run dev
```

Stop:

```powershell
docker compose -f docker/docker-compose.yml down
```

## Path B — Infra Compose + host venv (DH classic)

```powershell
# 1) Dependencies only
docker compose -f docker/docker-compose.yml up -d postgres redis postgres_ro

# 2) Env
copy .env.example .env   # first time; edit secrets

# 3) Backend venv + migrate
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head

# 4) API (terminal A)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5) Worker (terminal B) — required for Analyze runs
.\.venv\Scripts\python.exe -m app.workers.analysis_worker

# 6) Frontend (optional, terminal C)
cd ..\frontend
npm run dev
```

## Health probes (API only)

| Probe | URL | Meaning |
|-------|-----|---------|
| Liveness | `GET /health/live` | Process up |
| Readiness | `GET /health/ready` | **DB + Redis** ok (503 if not) |
| Compat | `GET /health` | Same as ready |

**Worker:** no HTTP health. Verify by:

1. Process / container running (`analysis_worker` / `aibi-worker`)  
2. Startup log includes `max_inflight` / `queue_max_depth`  
3. After enqueue, Run leaves `pending` → `running` / terminal  
4. Redis `PING` via ready probe on API  

## Release gate (before claiming Demo “green”)

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\smoke_release_gate.py
```

- Always: alembic head + Kernel / skill lifecycle / **data.profile** / **wave3 platform** / task events / docker compose / M2 / M4 / M5 / M6 / E3 / auth / rate / metrics / openapi / repair / cost budget / schema linking  
- **HITL:** H1 + H2 suite (`t1_approve_api` → `t2_resume_cas` → `t3_execute` → `t4_mock_runtime` → `t5_snapshot`); gate resets in-flight capacity between H2 smokes  
- Evals: **core** + **quality** + **profile** (regression vs baselines when present)  
- **M3:** only if `POSTGRES_RO_DSN` is set; otherwise skipped  
- Optional planes: see [DATA_PLANE.md](./DATA_PLANE.md) · [OIDC.md](./OIDC.md) · [MCP.md](./MCP.md)  
- On failure: look for `GATE FAIL: stage=<label>` (stage names identify the failing smoke)

### CI (T-13)

GitHub Actions: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)

- Triggers: `push` / `pull_request` on `main` | `master`
- Services: Postgres **5433** + Redis **6379**
- Steps: `pip install` → `docker compose config` → `smoke_docker_compose` → compose `postgres_ro` → `smoke_release_gate`
- **Not in CI:** full `api`/`worker` image build+up, live LLM calls, frontend build, deploy/CD


## Observability note (DH.5)

Worker / enqueue logs include `run_id`, `status`, `failure_class`, `skill_id` for join with:

`GET /api/v1/workspaces/{ws}/tasks/{run_id}/execution`

**Trace remains the execution truth**; logs are operator correlation only.

## Out of this runbook

APM/SIEM · Worker HTTP · Frontend-in-Compose · cloud deploy / CD · Runtime deferred features (workspace cap / replay_of)
