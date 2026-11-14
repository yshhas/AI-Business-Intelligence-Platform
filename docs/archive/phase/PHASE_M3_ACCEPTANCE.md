# Phase M3 — Connector Thin Slice Acceptance

**Status:** ✅ **Frozen** — see [PHASE_M3_RETROSPECTIVE.md](PHASE_M3_RETROSPECTIVE.md)  
**Prerequisite:** M1 + M2 remain frozen  
**Theme:** Same Enterprise Data Agent Runtime on Postgres read-only data plane

## Proof

> 同一个 Runtime / Tool / Policy / Run governance，可在 `file`（DuckDB）与 `postgres_ro` 两个数据面上运行。

## Delivered

| Item | Detail |
|------|--------|
| Executor | `backend/app/services/postgres_ro_service.py` (Gate + RO session) |
| Branch | `agent_runtime` switches on `Dataset.source_type` |
| Bind API | `POST /api/v1/workspaces/{id}/datasets/postgres-ro` |
| Metadata | `source_type=postgres_ro`, `source_config_json.allowed_tables` (≤2), keep `duckdb_table` as primary |
| DSN | Env `POSTGRES_RO_DSN` only (separate from `DATABASE_URL`) |
| Gate | Schema-qualified `public.table` extraction/allowlist |
| failure_class | `connector_error` |
| Fixture | `docker` service `postgres_ro` + `docker/postgres_ro_init/` |
| UI | Minimal bind form on Datasets page; Analyze shows `source_type` |

## Acceptance checklist

- [x] Gate schema-qualified allowlist + deny non-allowlist / bare names (`smoke_m3_connector.py`)
- [x] Bind `postgres_ro` + heuristic/LLM Analyze path succeeds; `platform.data_plane.source_type=postgres_ro`
- [x] Gate reject maps to `policy_denied`; `ConnectorError` → `connector_error`
- [ ] `file` upload → Analyze still succeeds (manual regression / existing M1-M2 smokes)
- [ ] Stop RO Postgres mid-run → `connector_error` (manual)
- [ ] timeout / cancel on postgres_ro path (manual; Worker unchanged)
- [x] No Connector Registry in Kernel; DSN only via env

## How to verify locally

```powershell
docker compose -f docker/docker-compose.yml up -d postgres_ro
# Ensure .env has POSTGRES_RO_DSN (see .env.example) — separate from DATABASE_URL
cd backend
.\.venv\Scripts\python -m alembic upgrade head
cd ..
$env:POSTGRES_RO_DSN="postgresql://aibi_ro:aibi_ro_password@localhost:5434/aibi_data"  # if not in .env
.\backend\.venv\Scripts\python backend/scripts/smoke_m3_connector.py
```

## Explicit non-goals (still out)

Connector Framework, multi-source product, writes/CDC/sync/Catalog, second Skill, Celery, Retry engine, Audit service, IAM.

## Limitations

- Cooperative timeout/cancel may not abort in-flight Postgres queries
- Single Demo DSN / connection_ref=`default`
- Fixed schema `public` only; allowlist ≤2 tables
