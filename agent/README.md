# Agent package — Enterprise Data Agent Platform

## Positioning

- **Platform:** Agent Kernel (`agent/kernel`)
- **Skills:** `data.bi` (Text-to-SQL) · `data.profile` (deterministic dataset profile)
- **Facade:** `agent.runtime.run_analysis` → `kernel.run(skill_id=ctx.skill_id)`

Backend workers must import **only** `agent.runtime.run_analysis` (or `agent.kernel.runtime.run`).  
Do **not** import `graph` / `nodes` / `skills` internals from product code.

## Public entry

```python
from agent.runtime import run_analysis
from agent.state import AnalysisContext

ctx.skill_id = "data.bi"  # or "data.profile"
outcome = run_analysis(ctx)  # AnalysisOutcome + legacy result_json
```

```python
from agent.kernel.runtime import run, platform_info
from agent.kernel.types import RunRequest

result = run(RunRequest(skill_id="data.profile", ...))  # RunResult
```

## Layout

```text
agent/
  kernel/                # types, registry, runtime, tools, policies, execution_trace
  skills/data_bi/        # Text-to-SQL LangGraph skill
  skills/data_profile/   # Deterministic profile skill (same Kernel contracts)
  gates/                 # SQL Gate (Policy + Data Plane defense-in-depth)
  guardrails.py          # Thin output redaction (Wave 3)
  data_plane.py          # Plane source_type markers (Wave 3)
  graph.py / nodes/      # data.bi implementation details
  prompts_sql.py         # Text-to-SQL prompts (versioned; see PROMPT_SQL_VERSION)
  schema_linking.py      # Schema Linking Lite (before generate_sql)
  llm_client.py          # HTTP LLM transport
```

## Graph (inside `data.bi`)

```text
load_context → link_schema → generate_sql → validate_sql → execute_sql
           → summarize → build_charts → write_report
```

- `link_schema` (v2): token overlap + builtin/injected synonyms; may route to `fail`
- `validate_sql` / `execute_sql` may retry `generate_sql` up to `max_retries` (repair_class tagged)
- Policy `sql.select_gate` is mandatory before `sql.execute_select` (plus plane `run_select` re-gate)

## `data.profile` (Wave 3)

```text
load_context → profile_schema (Policy SELECT aggregates) → summarize → write_report
```

Same Worker / Lifecycle / Trace path as `data.bi`. Charter: `docs/SKILL_DATA_PROFILE_CHARTER.md`.

## Lifecycle settings

| Env | Skill |
|-----|-------|
| `SKILL_DATA_BI_ENABLED` / `SKILL_DATA_BI_VERSION` | `data.bi` |
| `SKILL_DATA_PROFILE_ENABLED` / `SKILL_DATA_PROFILE_VERSION` | `data.profile` |
