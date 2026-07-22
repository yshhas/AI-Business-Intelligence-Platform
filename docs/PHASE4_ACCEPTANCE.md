# Phase 4 Acceptance — slim Text-to-SQL

**Status**: smoke-verified (heuristic path, no LLM required)  
**Date**: 2026-07-21

## Architecture

```text
API create task → Redis queue → Worker
  ├─ ANALYSIS_RUNTIME=mock  → mock_runtime (Phase 3 preserved)
  └─ ANALYSIS_RUNTIME=agent → agent_runtime → agent.runtime.run_analysis
                              │
                              └─ LangGraph: load → generate → validate(Gate)
                                            → execute(run_select+Gate) → summarize
```

## Contracts

- Worker only imports `agent.runtime.run_analysis` (+ builds `AnalysisContext`)
- Every DuckDB analysis query goes through `duckdb_service.run_select` → SQL Gate
- `result_json`: `{ summary, sql, table_preview, charts:[], limitations, mock }`

## Verified

| Check | Result |
|-------|--------|
| SQL Gate allow/deny | `GATE_OK` |
| `run_select` rejects DROP | `RUN_SELECT_GATE_OK` |
| Agent heuristic closed loop | `AGENT_RUNTIME_OK` |
| Mock runtime still present | `mock_runtime.py` unchanged path |

## Manual UI golden path

1. `.env`: `ANALYSIS_RUNTIME=agent`, `ALLOW_HEURISTIC_SQL=true`
2. Start postgres + redis, API, worker, frontend
3. Upload CSV with region/amount columns (or existing dataset)
4. Analyze → question like “按 region 汇总 amount”
5. Expect: steps timeline + SQL + preview rows; `mock=false`
