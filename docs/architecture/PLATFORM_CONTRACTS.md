# Enterprise Data Agent Platform — Contracts (M0 freeze)

**Status:** Frozen for M1 implementation; **M3 Data Plane addendum** in §10 (2026-07-22)  
**Companion:** [PLATFORM_CHARTER.md](PLATFORM_CHARTER.md)

These contracts define Kernel / Skill / Run / Artifact / Tool / Policy.  
M1 implements them with **behavior parity** for the existing BI golden path.

---

## 1. Skill contract

```text
skill_id:      "data.bi"          # stable
skill_version: "v1"               # optional in M1
display_name:  "Business Intelligence Analysis"
```

| Field | Rule |
|-------|------|
| `skill_id` | Required on every Run |
| Implementation | Existing LangGraph Text-to-SQL → charts → report |
| Registration | Kernel skill registry; M1 registers only `data.bi` |

A Skill declares which tools/policies it uses; it must **not** bypass Policy on side-effecting tools.

---

## 2. RunRequest

```json
{
  "skill_id": "data.bi",
  "workspace_id": "<uuid>",
  "input": {
    "question": "string",
    "dataset_id": "<uuid>"
  },
  "policy_context": {
    "allowed_tables": ["ds_..."],
    "default_limit": 200,
    "max_retries": 2
  },
  "runtime_hints": {
    "llm_api_key": "",
    "llm_base_url": "",
    "llm_model": "",
    "allow_heuristic_sql": true
  }
}
```

Notes:

- Product shell (Worker) builds this from `AnalysisTask` + `Dataset` + settings.
- `execute_select` callback / connector handle stays injected for DuckDB (no new Connector framework in M1).

---

## 3. RunResult

```json
{
  "success": true,
  "skill_id": "data.bi",
  "artifacts": [],
  "tool_calls": [],
  "policy_decisions": [],
  "limitations": [],
  "error_message": null
}
```

| Field | M1 requirement |
|-------|----------------|
| `skill_id` | **Required** stable field (API / RunResult) |
| `artifacts` | **Required** (may be empty on hard failure) |
| `tool_calls` | **Required** for real call chain (minimal tools only) |
| `policy_decisions` | At least Gate pass/fail summaries when validate/execute runs |
| `limitations` | Preserved from today’s semantics |

---

## 4. Artifact

Typed outputs. BI fields map as follows (compatibility projection → legacy `result_json`):

| `type` | Legacy field | Payload sketch |
|--------|--------------|----------------|
| `summary` | `summary` | `{ "text": "..." }` |
| `sql` | `sql` | `{ "sql": "..." }` |
| `table` | `table_preview` | `{ "columns": [], "rows": [] }` |
| `chart` | `charts[]` | ChartSpec (`bar` \| `line` only) |
| `report` | `report` | `{ "title", "markdown", "sections?" }` |

```json
{
  "type": "chart",
  "id": "chart_1",
  "payload": { }
}
```

**Compatibility:** Worker/API may continue to expose legacy `result_json` by projecting Artifacts.  
Optional non-blocking extension:

```json
"platform": {
  "skill_id": "data.bi",
  "artifact_types": ["summary", "sql", "table", "chart", "report"]
}
```

`result_json.platform` is **optional** for M1 (not a blocker).

---

## 5. ToolCall

```json
{
  "tool_id": "sql.execute_select",
  "status": "ok",
  "input_summary": { },
  "output_summary": { },
  "error_message": null,
  "latency_ms": 0
}
```

### M1 Tool Registry (minimal — real call chain only)

Do **not** invent empty tools for abstraction theater.

| `tool_id` | Maps to today | Side-effect class |
|-----------|---------------|-------------------|
| `llm.chat` | `agent.llm.chat_completion` | external |
| `sql.generate` | generate_sql path (LLM or heuristic) | compute / external |
| `sql.validate_policy` | SQL Gate check in validate node | none |
| `sql.execute_select` | DuckDB select via callback | read |
| `chart.build_spec` | heuristic ChartSpec | none |
| `report.build` | report builder (± LLM) | none / external |

**Rule:** `sql.execute_select` **must** run Policy `sql.select_gate` first (and existing `duckdb_service.run_select` defense-in-depth remains).

---

## 6. PolicyDecision

```json
{
  "policy_id": "sql.select_gate",
  "ok": true,
  "reason": null,
  "tool_id": "sql.execute_select"
}
```

| `policy_id` | Binding | Behavior |
|-------------|---------|----------|
| `sql.select_gate` | Before every `sql.execute_select` | Current deterministic SQL Gate; **not optional** |

No other policies required in M1.

---

## 7. Public entrypoints

```text
# Platform (M1 target)
kernel.run(RunRequest) -> RunResult

# Compatibility Facade (required)
run_analysis(AnalysisContext) -> AnalysisOutcome
    └── builds RunRequest(skill_id="data.bi")
    └── kernel.run(...)
    └── projects RunResult → AnalysisOutcome.result_json
```

Backend Worker should keep calling the Facade (or Kernel explicitly); **must not** import skill graph/nodes directly.

---

## 8. Audit (M1 stance)

- **No** new audit subsystem or audit tables in M1.
- Prefer extending existing `agent_run_steps` / `output_json` (and/or embedding `tool_calls` / `policy_decisions` in RunResult then persisting into steps).
- Evolve a dedicated audit store only when a real requirement appears.

---

## 9. Frontend (M1 stance)

- **No** large Tasks page redesign.
- Prefer stable fields on **API / RunResult** (`skill_id`, artifacts, tool/policy traces).
- Frontend: **minimal** Demo visibility (e.g. show `skill_id` or a short tool/policy hint) — UI must not lead platform capability.

---

## 10. Connector / Data Plane

### M1 stance (historical)

- DuckDB file tables remain the current data path.
- **No** premature multi-connector abstraction in M1.
- Injection of `execute_select` into the skill context stays as today.

### M3 addendum (frozen)

- Second plane: `source_type=postgres_ro` via Product Shell executor (not Kernel registry).
- Same rule: Policy `sql.select_gate` before execute; executor re-gates + read-only session.
- Allowlist: schema-qualified `public.table` (≤2); DSN from `POSTGRES_RO_DSN` only.
- **Still no** Connector Framework / multi-source product / write path.
- Optional non-secret echo: `result_json.platform.data_plane.{source_type, primary_table, allowed_tables}`.
- Infra failures: `failure_class=connector_error`.

---

## 11. Compatibility matrix

| Surface | M1–M3 rule |
|---------|------------|
| Redis queue / task states | Unchanged (M2 additive terminals only) |
| Auth / Workspace / Dataset main flows | Additive `postgres-ro` bind; upload unchanged |
| Legacy `result_json` keys | Preserved via projection |
| `ANALYSIS_RUNTIME=mock\|agent` | Preserved |
| SQL Gate strength | Must not weaken; schema-qualified names supported |
| Kernel contracts | Unchanged through M3 |
