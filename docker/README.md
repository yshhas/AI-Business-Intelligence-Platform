# Docker Compose

**T-12:** infra + **API** + **Worker** + optional **web** (nginx) in one compose file.

## Services

| Service | Purpose | Host port |
|---------|---------|-----------|
| `postgres` | Platform metadata DB | **5433** → 5432 |
| `redis` | Analysis task queue (List) | **6379** |
| `postgres_ro` | M3 RO demo data plane | **5434** → 5432 |
| `api` | FastAPI (`aibi-app:local`) | **8000** |
| `worker` | `analysis_worker` (same image) | **8001** (health) |
| `web` | nginx → static UI + `/api` proxy | **8080** → 80 |
| `prometheus` | Scrapes `api:8000/metrics` | **9090** (profile `obs`) |
| `grafana` | Dashboards (optional) | **3000** (profile `obs`) |

Shared volume: repo `data/` → `/app/data` (uploads + DuckDB) for both api and worker.

## Full stack

From **repo root**:

```powershell
copy .env.example .env   # once
docker compose -f docker/docker-compose.yml --env-file .env up -d --build
curl http://127.0.0.1:8000/health/ready
curl http://127.0.0.1:8080/health/ready   # via web proxy
```

UI: open **http://127.0.0.1:8080** (nginx serves SPA and proxies `/api` to `api:8000`).

Golden path: upload CSV → Analyze → Trace / Artifacts.

### Observability (optional)

```powershell
docker compose -f docker/docker-compose.yml --env-file .env --profile obs up -d prometheus grafana
```

Prometheus config: `docker/observability/prometheus.yml` → `api:8000/metrics`.

## Infra only (host venv API/Worker)

```powershell
docker compose -f docker/docker-compose.yml up -d postgres redis postgres_ro
```

Then run uvicorn + worker from `backend/.venv` (see [OPS_RUNBOOK.md](../docs/OPS_RUNBOOK.md) Path B).

## URLs

| Consumer | DATABASE_URL host | REDIS | POSTGRES_RO |
|----------|-------------------|-------|-------------|
| Host venv | `localhost:5433` | `localhost:6379` | `localhost:5434` |
| api / worker containers | `postgres:5432` | `redis:6379` | `postgres_ro:5432` |

Compose sets container URLs in `environment:` so they override localhost values from `.env`.

## Images

| Image | Dockerfile | Notes |
|-------|------------|-------|
| `aibi-app:local` | `docker/Dockerfile` | API + Worker (`APP_ROLE`) |
| `aibi-web:local` | `frontend/Dockerfile` | Node build → nginx |

- Entrypoint: `docker/entrypoint.py` — `APP_ROLE=api|worker|migrate`
- API runs `alembic upgrade head` then uvicorn; worker waits until API healthcheck passes
- nginx config: `docker/nginx.conf` (proxies `/api`, `/health`, `/metrics`)

```powershell
docker logs -f aibi-api
docker logs -f aibi-worker
docker logs -f aibi-web
```

See also [OBSERVABILITY.md](../docs/OBSERVABILITY.md) and [DUCKDB_TOPOLOGY.md](../docs/DUCKDB_TOPOLOGY.md).
