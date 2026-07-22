# Phase 3 checklist — async task skeleton (mock worker)

Stop line: no LangGraph, no LLM, no Text-to-SQL, no reports/charts, no real Agent.

Goal: analysis_tasks → Redis List queue → Worker → mock result (+ polling UI)

## Steps

- [x] **3.0** Redis Compose up + PING
- [x] **3.1** `analysis_tasks` + `agent_run_steps` migration
- [x] **3.2** Redis List queue helper
- [x] **3.3** Task REST APIs (create/list/get/steps) — enqueue only
- [x] **3.4** Worker mock runtime (no agent)
- [x] **3.5** Frontend polling (no SSE)
- [x] **3.6** Analyze + Tasks pages
- [x] **3.7** E2E acceptance (`pending` → `succeeded`, 3 mock steps, `mock=true`)

## Runtime

```env
ANALYSIS_RUNTIME=mock
REDIS_URL=redis://localhost:6379/0
ANALYSIS_QUEUE_KEY=aibi:analysis_tasks
```

## Processes

```powershell
# API
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Worker
python -m app.workers.analysis_worker
```
