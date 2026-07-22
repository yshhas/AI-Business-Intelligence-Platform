# E2 — Trace / Analyze Explainability (Implementation Checklist)

**Status:** ✅ **FROZEN** — [PHASE_E2_FINAL_STATUS.md](./PHASE_E2_FINAL_STATUS.md) · [ACCEPTANCE](./PHASE_E2_ACCEPTANCE.md)  
**Date:** 2026-07-22  
**Authorized candidate:** N1 ([PHASE_NEXT_CANDIDATES.md](./PHASE_NEXT_CANDIDATES.md))  
**Parents:** [ENHANCEMENT_ROADMAP.md](./ENHANCEMENT_ROADMAP.md) · E1-AC frozen ([FINAL_STATUS](./PHASE_E1_AC_FINAL_STATUS.md))

**Goal:** Make existing Run / Trace / Policy / Permission / linking / cost fields **understandable** so a user can answer:

1. Why was this SQL generated?  
2. Which schema (tables/columns) was used?  
3. Which step passed / was denied?  
4. How much resource was used?  
5. How were final Artifacts produced?

---

## 0. Decision lock

| Item | Decision |
|------|----------|
| Scope | **Product Shell UX + thin Trace API typing** only |
| Backend behavior | **No** new Skill nodes, retries, or Agent autonomy |
| N2 Eval stage CLI | **Not started** as a product; assess **light reuse** in §6 |
| SQL Repair / E1-B | Still deferred |

### Binding constraints

| Must | Must not |
|------|----------|
| Kernel / Worker / Policy / Data Plane unchanged | Chat UI / token streaming |
| Reuse existing Trace / steps / artifacts APIs | LangSmith dual-track Trace |
| Prefer explain existing fields over inventing new ones | Full Observability / Audit / Run Explorer product |
| Friendly copy for known HTTP errors (e.g. 429 budget) | Soften Gate rules or change `failure_class` semantics |

---

## 1. User questions → UI mapping

| # | User question | Primary sources (already exist unless noted) | E2 UI surface |
|---|---------------|-----------------------------------------------|---------------|
| Q1 | Why this SQL? | `result_json.sql` · step `generate_sql` · `platform.sql_quality.link_status/method/reason` · Gate retry `gate_error` in step input | **Why this SQL** block: link status + method + reason; linked columns; note “prompt used linked schema view” |
| Q2 | Which schema? | `sql_quality.selected_tables/columns` · `authorization.authorized_tables` · `data_plane` · dataset name | **Schema used** block: tables (authorized vs selected) + columns + `column_count_linked/full` |
| Q3 | Which step pass/deny? | `GET …/steps` · `execution.policy_decisions` · `execution.tool_calls` · `failure_class` / `policy_denied` | **Timeline** with human labels + pass/fail colors; Policy allow/deny + reason prominent |
| Q4 | How much resource? | `Task.llm_total_tokens` · step `latency_ms` · optional sum of step latencies | **Resources** line: tokens (if set) + wall/step latency summary |
| Q5 | How Artifacts produced? | `GET …/artifacts` + lineage · `execution.artifacts` refs · Skill graph order | **Artifacts** panel: type → lineage (skill/plane/dataset); optional “produced after execute → summarize → charts → report” hint |

---

## 2. Trace / API field → UI / API contract

### 2.1 Already returned (wire to UI)

| Field | API | Today in UI | E2 action |
|-------|-----|-------------|-----------|
| `skill_id` / `skill_version` | Task + `/execution` | Partial (skill id in result; version weak) | Header chips: skill + version |
| `source_type` / `data_plane` | Task + `/execution` | Partial | Header: plane |
| `failure_class` / `policy_denied` / `status` | Task + `/execution` | Shown raw | Keep + human short label map (display only) |
| `authorization` | `/execution` (service already) | **Not shown** | Show actor_role, authorized_tables, acl_mode |
| `execution.tool_calls` | `/execution` | Raw tool_id list | Keep; add human label beside tool_id |
| `execution.policy_decisions` | `/execution` | Shown | Emphasize deny + `reason` |
| `execution.artifacts` + summary | `/execution` | Listed | Cross-link to Artifacts panel |
| `llm_total_tokens` | `TaskOut` | **Not shown** | Resources line |
| Steps (`node_name`, status, latency, error) | `/steps` (+ SSE) | Raw node names | Human labels + expand brief for key nodes |
| Artifacts + `lineage` | `/artifacts` | Metadata + JSON dump | Clearer lineage sentence; collapse raw JSON by default |

### 2.2 Gap: `sql_quality` not in OpenAPI model (fix in E2)

| Field | Backend fact | Gap | E2 action |
|-------|--------------|-----|-----------|
| `platform.sql_quality` | Written by Facade; `get_execution_trace()` **includes** key | `ExecutionTraceOut` **omits** `sql_quality` → Pydantic strips it on `/execution` | Add optional `sql_quality: dict \| None` to `ExecutionTraceOut` + frontend `ExecutionTrace` |
| Same fields in `result_json.platform.sql_quality` | Present on Task result | `TaskResultPanel` ignores | Prefer Trace panel; optional echo under SQL in result |

**No new persistence / no Kernel change** — typing + projection only.

### 2.3 Canonical `sql_quality` shape (display)

```json
{
  "schema_version": 1,
  "link_status": "ok | partial | fallback_full | failed",
  "link_method": "token_overlap | fallback_full | identity",
  "link_reason": "string|null",
  "selected_tables": ["…"],
  "selected_columns": ["…"],
  "column_count_full": 20,
  "column_count_linked": 8
}
```

Display rules:

- Always show `link_status` when present (including `fallback_full` — **never hide degradation**).  
- `fallback_full` / `partial` / `failed` get distinct visual tone (warn / warn / error).  
- Columns as chip/list; truncate with “+N more” if long.

### 2.4 Step label map (display-only)

| `node_name` | Human label | User question |
|-------------|-------------|---------------|
| `load_context` | Load context | — |
| `link_schema` | Schema linking | Q1/Q2 |
| `generate_sql` | Generate SQL | Q1 |
| `validate_sql` | Policy Gate | Q3 |
| `execute_sql` | Execute SQL | Q3 |
| `summarize` | Summarize | Q5 |
| `build_charts` | Build charts | Q5 |
| `write_report` | Write report | Q5 |
| `fail` | Failed | Q3 |

Expand (default collapsed): for `link_schema` show selected_columns / link_status from `output_json`; for `validate_sql` show deny reason; for `generate_sql` show sql_draft snippet if present.

---

## 3. UX composition (Analyze — one Run panel)

Keep existing layout; **enrich**, don’t invent a second product.

```text
Task header
  status · failure_class (label) · skill@version · plane · tokens

Explainability strip (new — answers Q1–Q4 at a glance)
  Schema used | Why SQL (link) | Policy | Resources

ExecutionTracePanel (enriched)
  Authorization · sql_quality · Policy decisions · Tool calls · Artifact refs

ArtifactsPanel (clearer lineage; JSON collapsed)

TaskResultPanel
  SQL + preview… (optional tiny “linked N/M columns” note)

Steps timeline (human labels; expand key steps)
```

**TasksPage:** optional thin reuse — show `failure_class` + `llm_total_tokens` in list row if cheap; **not** required for E2 exit (Analyze-first).

**429 / budget / capacity:** map known `failure_class` / API errors to one-line Chinese/English copy on Analyze submit (Shell only).

---

## 4. Frontend / backend impact range

### 4.1 Backend (thin)

| Path | Change |
|------|--------|
| `backend/app/schemas/task.py` | Add `sql_quality` to `ExecutionTraceOut` |
| `backend/app/services/task_service.py` | Already returns `sql_quality` — verify unchanged |
| Smoke | Extend or add `smoke_e2_explainability.py` **or** thin assert in existing M4/P1 smoke that `/execution` includes `sql_quality` when result has it |

**Out of scope:** Worker, Kernel, Gate, ACL logic, cost_budget enforcement, Eval suites.

### 4.2 Frontend

| Path | Change |
|------|--------|
| `frontend/src/types/task.ts` | `sql_quality` on `ExecutionTrace`; maybe typed helpers |
| `frontend/src/components/ExecutionTracePanel.tsx` | Authz + sql_quality + clearer policy/tools |
| `frontend/src/components/TaskResultPanel.tsx` | Optional link note under SQL; show tokens if passed as prop **or** read from parent Task |
| `frontend/src/components/ArtifactsPanel.tsx` | Lineage sentence; collapse raw JSON |
| `frontend/src/pages/AnalyzePage.tsx` | Header chips; explainability strip; step labels; 429 copy; pass tokens into panels |
| Optional small util | `frontend/src/lib/traceLabels.ts` — node/failure_class labels |

### 4.3 Docs / gate

| Path | Change |
|------|--------|
| `docs/PHASE_E2_*` | Checklist + acceptance after implement |
| `docs/PHASES.md` / Roadmap | Point to E2 when done |
| `smoke_release_gate.py` | Wire E2 smoke if added |

---

## 5. Implementation checklist (when authorized to code)

### API contract

- [ ] `ExecutionTraceOut.sql_quality` optional field  
- [ ] Frontend type + fetch already via `getTaskExecution` picks up field  
- [ ] Confirm no strip of `authorization` / `sql_quality` in OpenAPI response  

### Analyze header & errors

- [ ] Chips: status, failure_class (labeled), skill@version, plane, `llm_total_tokens`  
- [ ] Friendly copy for budget/capacity 429 / known failure_class  

### Explainability strip + Trace panel

- [ ] Schema used (selected + authorized tables; columns; counts)  
- [ ] Why SQL (link_status/method/reason; never hide fallback)  
- [ ] Policy allow/deny + reason  
- [ ] Resources (tokens + latency summary from steps)  

### Steps & Artifacts

- [ ] Human labels for node_name  
- [ ] Expandable brief for link_schema / validate_sql / generate_sql  
- [ ] Artifacts lineage readable; raw JSON collapsed by default  

### Quality bar

- [ ] Smoke or manual script: execution JSON contains sql_quality when platform has it  
- [ ] No Kernel/Worker/Policy/Plane diffs beyond Trace schema field  
- [ ] SSE remains task/steps only (no token stream)  

---

## 6. N2 light reuse (eval — no separate CLI this round)

| Observation need | E2 reuse | Still not N2 |
|------------------|----------|--------------|
| Failure stage (link vs generate vs execute) | Steps timeline + “first error step” one-liner derived from `/steps` | No `eval_link_report.py`; no suite changes |
| link_ok / fallback visibility | UI shows same enums as Eval | No baseline/CLI aggregation |

**Verdict:** E2 may show **first failing step label** for Demo/debug. Full Eval attribution CLI stays **shelf** until explicitly authorized.

---

## 7. Acceptance criteria (exit)

| # | Criterion |
|---|-----------|
| A1 | Successful agent Run: UI shows `link_status` + `selected_columns` (from `/execution.sql_quality` or equivalent) |
| A2 | `fallback_full` / `failed` visibly distinct — not presented as plain success linking |
| A3 | Policy deny Run: Gate `reason` visible without opening raw JSON |
| A4 | Authorization: `actor_role` + `authorized_tables` visible when present |
| A5 | `llm_total_tokens` shown when Task has it; step latencies remain visible |
| A6 | Artifacts show type + lineage (skill/plane/dataset) with collapsed raw payload |
| A7 | Steps use human labels for core graph nodes including `link_schema` |
| A8 | No Chat / streaming / LangSmith / new Agent behavior; Kernel/Worker/Policy/Plane unchanged |
| A9 | Release smoke (or documented manual) covers Trace `sql_quality` on execution API |

---

## 8. Explicit won't-do (this E2)

- SQL Repair / `repair_class` UI as if shipped  
- Chat UI, token streaming, WebSocket redesign  
- LangSmith / dual Trace exporters  
- Observability platform, metrics dashboards, Eval SaaS  
- Run Explorer / Audit Center product  
- New Kernel tools, Policy rules, Data Plane sources  
- Changing `failure_class` vocabulary  
- ACL admin UI (P1 freeze)  
- Standalone N2 Eval stage CLI (unless later authorized)  
- Redesigning Analyze into a multi-page “ops console”

---

## 9. Decision gate

| Option | Meaning |
|--------|---------|
| **Confirm E2 as written** | Proceed to implement this checklist |
| **Revise strip / omit TasksPage** | Adjust scope then code |
| **Require smoke_e2 before UI** | Order preference only |

**Awaiting confirmation — no coding until approved.**
