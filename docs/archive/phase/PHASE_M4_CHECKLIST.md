# Phase M4 — Traceable Execution Model Checklist（仅设计，待确认后编码）

**Status:** ✅ **Frozen** — see [PHASE_M4_ACCEPTANCE.md](PHASE_M4_ACCEPTANCE.md) / [PHASE_M4_RETROSPECTIVE.md](PHASE_M4_RETROSPECTIVE.md)  
**Era:** 2 — Enterprise Capability Enhancement  
**Prerequisite:** Era 1 Foundation frozen (M1–M3 boundaries unchanged)  
**Theme:** Audit / Observability as **Traceable Execution Model** (not an Audit product)  
**Parent:** [ENTERPRISE_CAPABILITY_ROADMAP.md](../roadmap/ENTERPRISE_CAPABILITY_ROADMAP.md) · [ENTERPRISE_M4_M6_RANKING.md](../roadmap/ENTERPRISE_M4_M6_RANKING.md)

**Confirmed open points (2026-07-22)**
| # | Decision |
|---|----------|
| 1 Persistence | `platform.execution` JSON + thin denormalized columns; no events table |
| 2 API | `GET /tasks/{id}/execution` |
| 3 List | Extend `GET /tasks` filters: skill_id, source_type, status, policy_denied |
| 4 Facade | New `to_execution_trace()` (not pile into legacy projection) |
| 5 Partial runs | Best-effort keep tool/policy/artifact refs; incomplete OK |
| 6 skill_version | Omit for now; `skill_id` only |

**Goal**

> 把已有 Run / ToolCall / PolicyDecision / Artifact / Failure Class 统一为**可查询的执行追溯模型**，能回答企业问题——而不是新增一个 Audit 页面或日志系统。

**Enterprise questions M4 must answer (per Run)**

1. 这次 Agent Run 做了什么？  
2. 调用了哪些工具？  
3. 哪些 Policy 生效？  
4. 为什么允许 / 拒绝？  
5. 最终产生了哪些 Artifact？  

**Hard stop-lines**

- No Audit microservice / SIEM / log-platform rebuild  
- No new event bus; no parallel “audit_events” product schema unless strictly required for query (prefer extend existing)  
- No Kernel boundary change (still Skill dispatch only)  
- No M5 IAM / invite; no M6 Artifact CMS; no Connector Framework / second Skill / Multi-Agent  
- Keep `/tasks` API compatibility; Trace is a **view/model** on Run  

---

## 0. Architecture invariant

```text
Worker persists Run (analysis_tasks) + Steps (agent_run_steps)
        +
Kernel RunResult { tool_calls, policy_decisions, artifacts }
        ↓
M4 Trace Model (structured, queryable projection)
        ↓
Trace Query API + minimal Demo UI
```

| Layer | M4 role |
|-------|---------|
| Kernel | Keep producing `ToolCallRecord` / `PolicyDecision` / `Artifact` (may add stable ids only if needed) |
| Worker / Facade | **Materialize** execution snapshot into persisted Run |
| Product Shell API | Query / get trace |
| UI | Minimal Run Trace panel |

---

## 1. As-is: steps + platform JSON (Foundation)

### 1.1 Persisted today

| Store | Content | Strength | Gap vs Trace Model |
|-------|---------|----------|--------------------|
| `analysis_tasks` | status, `failure_class`, `result_json`, timestamps | Run identity + terminal | No first-class tool/policy/artifact arrays for query |
| `result_json.platform` | `skill_id`, `tool_ids[]`, `policy_ids[]`, `run{}`, `data_plane{}` | Demo hints | **IDs only** — no allow/deny reason, no per-call status |
| `result_json` legacy | summary/sql/table/charts/report | Human outputs | Artifacts flattened; lineage weak |
| `agent_run_steps` | graph `node_name`, I/O JSON, latency; some `tool_id`/`policy_id` in `output_json` | Timeline | Node-centric ≠ Tool/Policy/Artifact model; hard to query across Runs |

### 1.2 In-memory then dropped (mostly)

`RunResult.tool_calls` / `policy_decisions` / `artifacts` exist in Kernel Skill execution, but Facade `to_legacy_result_json()` **collapses** them to id lists + legacy fields — full records are **not** systematically persisted.

### 1.3 Association today (weak)

```text
Run (task_id)
  ├─ steps[]          (ordered nodes; optional tool_id in output)
  ├─ platform.tool_ids[] / policy_ids[]   (sets, no join keys)
  └─ legacy artifact fields               (no artifact.id required)
```

Cannot reliably answer “which PolicyDecision denied which ToolCall” from DB alone after the process exits (except partial step text).

---

## 2. Target: Traceable Execution Model (to-be)

### 2.1 Vocabulary

| Term | Meaning | Source of truth (M4) |
|------|---------|----------------------|
| **ExecutionTrace** | One Run’s governed execution record | Persisted on Run (+ steps as timeline appendix) |
| **ToolCall** | One tool invocation | From `ToolCallRecord` (+ seq) |
| **PolicyDecision** | One policy evaluation | From `PolicyDecision` (+ seq, link to tool) |
| **ArtifactRef** | One typed output | From `Artifact` (+ stable id) |
| **Run** | Lifecycle object | Existing task row (`run_id = task.id`) |

Product path may still say `/tasks`; docs/API Trace resources say **Run**.

### 2.2 Canonical shape (design)

Persist under `result_json.platform.execution` (name TBD; avoid new table unless query forces it):

```json
{
  "platform": {
    "skill_id": "data.bi",
    "skill_version": "v1",
    "data_plane": { "source_type": "postgres_ro", "primary_table": "public.demo_orders", "allowed_tables": [] },
    "run": { "run_id": "...", "status": "failed", "failure_class": "policy_denied", "...": "..." },
    "execution": {
      "schema_version": 1,
      "tool_calls": [
        {
          "call_id": "tc_1",
          "seq": 1,
          "tool_id": "sql.validate_policy",
          "status": "ok",
          "latency_ms": 2,
          "input_summary": {},
          "output_summary": {},
          "error_message": null,
          "step_no": 3
        }
      ],
      "policy_decisions": [
        {
          "decision_id": "pd_1",
          "seq": 1,
          "policy_id": "sql.select_gate",
          "ok": false,
          "reason": "Table 'public.secret' is not in allowlist ...",
          "tool_id": "sql.execute_select",
          "call_id": "tc_4",
          "step_no": 4
        }
      ],
      "artifacts": [
        {
          "artifact_id": "art_sql_1",
          "type": "sql",
          "ref": { "field": "sql" }
        }
      ],
      "summary": {
        "tool_count": 5,
        "policy_deny_count": 1,
        "artifact_types": ["summary", "sql", "table"]
      }
    }
  }
}
```

**Backward compatible:** keep existing `tool_ids` / `policy_ids` / legacy artifact fields; `execution` is additive.

### 2.3 Correlation rules (must define in coding kickoff)

| Link | Rule |
|------|------|
| `run_id` | Always `analysis_tasks.id` |
| `ToolCall.call_id` | Stable within Run: `tc_{seq}` (or uuid) assigned at materialization |
| `PolicyDecision.call_id` | When decision is about a tool invoke, point to that `ToolCall.call_id`; validate-node decisions may set `tool_id=sql.validate_policy` and `call_id` of that call |
| `PolicyDecision.reason` | Required on `ok=false`; short Gate/Policy message (no secrets) |
| `Artifact.artifact_id` | Prefer existing `Artifact.id`; else `art_{type}_{n}` |
| `step_no` | Best-effort link to `agent_run_steps.step_no` when known |
| Timeline | Steps remain the **ordered narrative**; execution arrays are the **enterprise-query model** |

### 2.4 Materialization point (recommended)

| When | Who | What |
|------|-----|------|
| Skill success/fail | Facade or Worker after `run_analysis` | Build `execution` from `RunResult` (needs Facade to pass full records — today only legacy projection) |
| Lifecycle terminal | Worker `attach_run_platform` | Merge `run` + preserve `execution` |
| Cancel/timeout before Skill finish | Worker | `execution` may be partial/empty; steps may still exist; `failure_class` still set |

**Facade change (minimal, not Kernel rewrite):**  
`to_legacy_result_json` (or sibling) should embed full `tool_calls` / `policy_decisions` / artifact refs into `platform.execution`, not only id lists.

**Kernel:** Prefer **no** structural change; optional: ensure Artifact.id filled for chart/report. Do **not** add observability SDK into Kernel.

---

## 3. Evolution path: steps vs execution

| Concern | Keep in steps | Put in execution |
|---------|---------------|------------------|
| Graph node order / debug | Yes | Optional `step_no` only |
| Tool allow/deny + reason | Partial today | **Yes (canonical)** |
| Policy decisions | Partial | **Yes (canonical)** |
| Artifact inventory | No | **Yes** |
| Large previews / row samples | Cap/summarize in steps | **Do not** dump large tables into execution |
| Cross-run filter | Weak | Via task columns + execution.summary flags |

**Rule:** Execution summaries stay **small** (summaries, reasons, ids). Heavy payloads stay in legacy `result_json` / step I/O with existing size discipline.

### 3.1 Do we need a new table?

| Option | Pros | Cons | M4 recommendation |
|--------|------|------|-------------------|
| **A. JSON snapshot only** (`platform.execution`) | No migration risk; matches “no audit product” | Filter by deny/plane needs JSON query or denormalized columns | **Default** |
| **B. Additive columns** on `analysis_tasks` | Fast list filters | Extra migration | **Recommended companion:** e.g. `source_type`, `skill_id`, `policy_denied` bool (denormalized from execution) |
| **C. `execution_events` table** | Normalized | Looks like audit product; join tax | **Out of M4** unless A+B proven insufficient |

**M4 choice:** **A + thin B** (2–4 denormalized filter columns). No event table.

Suggested columns (design):

| Column | Purpose |
|--------|---------|
| `skill_id` | Filter (default `data.bi`) |
| `source_type` | From data plane (`file` / `postgres_ro` / null) |
| `policy_denied` | bool — any policy `ok=false` |
| (existing) `failure_class`, `status` | Already filterable |

---

## 4. API query boundary

### 4.1 Keep

| API | Role |
|-----|------|
| `GET .../tasks/{id}` | Run header + `result_json` (includes execution) |
| `GET .../tasks/{id}/steps` | Timeline appendix |

### 4.2 Add (M4 minimal)

| API | Purpose |
|-----|---------|
| `GET .../tasks` (extend query params) **or** `GET .../runs/query` | Filter list: `status`, `failure_class`, `source_type`, `policy_denied`, time range |
| `GET .../tasks/{id}/execution` **or** `.../trace` | Return **ExecutionTrace** view only (execution + run + data_plane + skill), without forcing UI to parse full legacy blob |

**Auth (M4):** workspace member only (same as tasks). Resource-level visibility = **M5**. Do not invent share links.

**Naming recommendation:**  
- External: keep `/tasks` + add `/tasks/{id}/execution`  
- Docs: call response **ExecutionTrace**  
- Optional alias later: `/runs/...` (not required in M4)

### 4.3 Query semantics

| Filter | Behavior |
|--------|----------|
| `failure_class=policy_denied` | Task column match |
| `policy_denied=true` | Denormalized flag OR JSON path |
| `source_type=postgres_ro` | Denormalized / data_plane |
| List default | Recent N Runs for workspace; include short summary fields for Demo |

### 4.4 Export (thin)

| Form | M4 |
|------|-----|
| `GET .../execution?format=json` | Same trace document |
| CSV/PDF compliance pack | **Out** |

No bulk “audit log drain” product.

---

## 5. UI minimal Demo scope

### 5.1 In scope (minimal)

| Surface | Show |
|---------|------|
| Task / Analyze result | **Run Trace** section: skill, plane, status, `failure_class` |
| Same panel | Tool calls list (id, status, latency) |
| Same panel | Policy decisions (ok/deny + **reason** on deny) |
| Same panel | Artifact types / ids (link to existing summary/sql/chart/report blocks) |
| Tasks list (optional light) | Badge: `policy_denied` / `connector_error` / `source_type` |

### 5.2 Out of UI scope (M4)

| Do not |
|--------|
| Standalone “Audit Center” IA / new top-level product nav mega-app |
| Log search like Kibana |
| Real-time tailing |
| Cross-workspace admin audit console |
| Diff two Runs UI |

**Principle:** Trace lives **next to the Run**, not as a separate Audit product.

---

## 6. Mapping Foundation → Trace (concrete)

| Enterprise question | Trace field |
|---------------------|-------------|
| Run did what? | `run` + `execution.summary` + steps timeline |
| Which tools? | `execution.tool_calls[]` |
| Which policies? | `execution.policy_decisions[]` |
| Why allow/deny? | `policy_decisions[].ok` + `.reason` (+ linked `call_id`) |
| Which artifacts? | `execution.artifacts[]` + legacy payloads for content |
| Plane? | `data_plane` |
| Terminal why? | `failure_class` + `error_message` |

---

## 7. Explicit non-goals (M4) — 不做 Audit 产品化

| Do not |
|--------|
| Audit microservice / separate deployable |
| SIEM / immutable WORM / compliance certification kit |
| Rebuild logging (stdout/file shippers, ELK) |
| `execution_events` normalized audit warehouse (M4) |
| PII redaction product (basic: never store DSN; reuse existing summary caps) |
| OpenTelemetry full APM (optional later; not M4) |
| M5 resource ACL beyond existing membership |
| M6 artifact retention CMS |
| Second Skill / Multi-Agent / Connector Framework |

---

## 8. Implementation steps (when coding starts)

| Step | Deliverable |
|------|-------------|
| **M4.0** | Spec freeze (this checklist + open points) |
| **M4.1** | Facade/Worker: materialize `platform.execution` from `RunResult` |
| **M4.2** | Correlation: call_id / decision_id / artifact_id / step_no rules + tests |
| **M4.3** | Migration: denormalized filter columns (thin) |
| **M4.4** | API: list filters + `GET .../execution` |
| **M4.5** | UI: Run Trace panel (minimal) |
| **M4.6** | Smoke: policy deny → reason in execution; list filter; Foundation regression |
| **M4.7** | Acceptance + freeze M4 |

---

## 9. Acceptance criteria (Definition of Done)

- [ ] For a succeeded Run: execution lists tools, policies, artifacts; answers Q1–Q5  
- [ ] For `policy_denied`: decision `ok=false` + **non-empty reason**; linked tool/call when applicable  
- [ ] `failure_class` / `data_plane` visible on same Trace  
- [ ] List filter by at least: `failure_class`, `source_type` or `policy_denied`  
- [ ] `GET .../execution` returns Trace without requiring Audit product UX  
- [ ] No Audit microservice; no SIEM; Kernel boundaries unchanged  
- [ ] M1–M3 smokes still green; legacy `result_json` fields preserved  
- [ ] UI: Trace on Run detail only (no Audit Center)

---

## 10. Open points for confirmation before coding

1. **Persistence:** confirm **JSON `platform.execution` + thin denormalized columns** (recommended) vs events table?  
2. **API path:** `GET /tasks/{id}/execution` (recommended) vs `/trace` naming?  
3. **List filters:** extend `GET /tasks` query params vs new `/runs/query`?  
4. **Facade:** enrich `to_legacy_result_json` in-place vs new `to_execution_trace()` helper used by Worker?  
5. **Partial runs** (cancel/timeout): empty execution vs best-effort partial tool_calls from steps?  
6. **skill_version:** always `"v1"` string in M4, or omit until Skill lifecycle?

---

## 11. One-line summary

> M4 turns Foundation side-effects into a **Traceable Execution Model**: one Run document that correlates ToolCalls, PolicyDecisions, and Artifacts — queryable and Demo-visible — without building an Audit product.
