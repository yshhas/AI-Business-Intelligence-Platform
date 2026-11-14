# Phase 2 checklist — CSV/Excel → DuckDB → schema/preview

Stop line: no Agent/LangGraph, no Redis worker, no analysis_tasks, no reports.
Do not modify Phase 1 Auth/Workspace behavior.

## Steps

- [x] **2.0** Storage paths + config (`storage_paths.py`, docs, gitignore)
- [x] **2.1** `datasets` model + Alembic `0002_phase2_datasets`
- [x] **2.2** `duckdb_service` (import / schema / preview) — no HTTP in service
- [x] **2.3** Upload API + `dataset_service` orchestration
- [x] **2.4** List / detail / preview APIs (DELETE deferred)
- [x] **2.5** Frontend Datasets page
- [x] **2.6** E2E API acceptance (upload → schema → preview)

## Conventions

| Kind | Path |
|------|------|
| Uploads | `data/uploads/{workspace_id}/{dataset_id}_{filename}` |
| DuckDB | `data/duckdb/{workspace_id}.duckdb` |
| Table | `ds_{uuid_hex}` |

Excel MVP: `.xlsx`, first sheet only.
