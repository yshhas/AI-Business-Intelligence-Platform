# Database conventions

## Connection (dialect-agnostic app code)

- Runtime URL: `DATABASE_URL` in repo-root `.env`
- Engine factory: `backend/app/core/db.py`
- Dialect quirks only: `backend/app/core/db_dialect.py`
- Models / services / routes **must not** branch on SQLite vs PostgreSQL

## Current local setup (Phase 1)

```env
DATABASE_URL=postgresql+psycopg://aibi:aibi_dev_password@localhost:5433/aibi
```

Compose: `docker compose --env-file ../.env up -d postgres`  
Host port **5433** → container 5432 (avoids clash with other local Postgres on 5432).

SQLite (`data/aibi_phase1.db`) is **legacy smoke only** — not the runtime DB.

### Dialect switch checklist

1. Start Compose Postgres  
2. Set `DATABASE_URL` to Postgres  
3. `alembic upgrade head`  
4. Restart API — no model/service changes required  

## Migrations

- Alembic under `backend/alembic/`
- Phase 1 revision: `0001_phase1_auth` (`users`, `workspaces`, `workspace_members`)
- Phase 2 revision: `0002_phase2_datasets` (`datasets`) — in progress

## DuckDB + uploads (Phase 2)

| Kind | Path convention |
|------|-----------------|
| Uploads | `data/uploads/{workspace_id}/{dataset_id}_{sanitized_filename}` |
| DuckDB file | `data/duckdb/{workspace_id}.duckdb` |
| Table name | `ds_{uuid_hex}` |

- Config: `UPLOAD_DIR`, `DUCKDB_DIR` (relative → **repo root** via `app.core.storage_paths`)
- Helpers: `backend/app/core/storage_paths.py`
- Analytics data stays in DuckDB; only dataset **metadata** belongs in PostgreSQL.

Excel MVP: `.xlsx`, **first sheet only**.
