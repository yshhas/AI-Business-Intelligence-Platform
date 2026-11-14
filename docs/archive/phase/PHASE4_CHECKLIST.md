# Phase 4 checklist — Text-to-SQL slim LangGraph (no reports/charts)

Stop line: keep mock runtime; no reports/charts/multi-agent; Auth/Workspace/Dataset main flow untouched.
SQL Gate must run before every DuckDB analysis query.

## Steps

- [x] **4.0** Config + agent package skeleton
- [x] **4.1** Deterministic SQL Gate
- [x] **4.2** `duckdb_service.run_select` (gate-enforced)
- [x] **4.3–4.4** LangGraph slim + `agent.runtime.run_analysis`
- [x] **4.5** Worker `ANALYSIS_RUNTIME=mock|agent`
- [x] **4.6** Frontend show sql + preview
- [x] **4.7** Golden path acceptance (smoke scripts + heuristic path)

## Runtime

```env
ANALYSIS_RUNTIME=agent   # or mock
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
SQL_DEFAULT_LIMIT=200
SQL_MAX_RETRIES=2
ALLOW_HEURISTIC_SQL=true
```

## Smoke

```powershell
cd backend
.\.venv\Scripts\python scripts\smoke_sql_gate.py
.\.venv\Scripts\python scripts\smoke_run_select_gate.py
.\.venv\Scripts\python scripts\smoke_agent_runtime.py
```

Expected: `GATE_OK` / `RUN_SELECT_GATE_OK` / `AGENT_RUNTIME_OK`
