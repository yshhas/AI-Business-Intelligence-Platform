# Phase 5 checklist — charts + short report (MVP)

Stop line: no new DB tables / task types; no Worker/Redis shell changes; no multi-agent.
Extend `result_json` only. Chart types: **bar + line**. `build_charts` = heuristic Spec (A).
Enhancement-layer failure → degrade + limitations; task may still succeed.

## Design choices (confirmed)

1. Charts: `bar` | `line` only (no pie)
2. ChartSpec: deterministic heuristic from preview; LLM may enhance title/rationale only
3. SQL/Gate fail → task failed; charts/report fail → succeeded + limitations

## Steps

- [x] **5.0** Contract: ChartSpec / Report / result_json
- [x] **5.1** `build_charts` node (heuristic)
- [x] **5.2** `write_report` node + graph edges
- [x] **5.3** Mock runtime placeholders
- [x] **5.4** Frontend charts + report
- [x] **5.5** Golden path + acceptance

## Graph

```text
… → execute_sql → summarize → build_charts → write_report → END
```

## Smoke

```powershell
cd backend
.\.venv\Scripts\python scripts\smoke_charts.py
.\.venv\Scripts\python scripts\smoke_agent_runtime.py
```
