# Phase M2 — Freeze + Retrospective

**Status:** ✅ **Formally closed / frozen** (2026-07-21)

## Narrative completed

```text
M1: Application → Platform + Skill
    Kernel · Skill · Tool · Policy · Artifact

M2: Platform → Governed Runtime
    Run lifecycle · timeout · cancel · failure classification
```

Together these form the core **Enterprise Data Agent Platform** story: a Data Skill can run, and an Agent Run can be governed.

## Freeze (do not expand now)

- No new Skill / Connector / Multi-Agent  
- No retry framework / Celery / distributed lease  
- No large UI redesign  
- No Audit product  

---

## Retrospective

### 1. Is the current Run model enough as a future AgentRun abstraction?

**Verdict: Yes, as a v1 AgentRun — with explicit seams.**

| Strength | Why it works |
|----------|----------------|
| First-class terminals | `succeeded / failed / cancelled / timed_out` are Demo-clear |
| Governance fields | `cancel_requested`, `failure_class`, `timeout_seconds` |
| Platform echo | `result_json.platform.run` ties Run to M1 skill/tool/policy |
| Separation | Lifecycle in Worker/task_service; Kernel stays Skill executor |

| Gap (acceptable for now) | Note |
|--------------------------|------|
| Resource still named `analysis_tasks` / `/tasks` | Semantic Run, physical Task — fine until a breaking rename is worth it |
| Cooperative timeout/cancel | Not a process isolator; documented limitations |
| No attempt/retry state | Intentional; “new Run = new task” |
| Steps ≠ structured ToolCall store | M1 audit-lite via steps JSON is enough |

**Recommendation:** Treat today’s task row + `platform.run` as **AgentRun v1**. Do not invent a parallel `agent_runs` table until a real second Skill or Connector forces a shared identity.

### 2. Task / Run naming migration — adjust now?

**Verdict: Do not rename APIs in the next phase.**

| Option | Pros | Cons |
|--------|------|------|
| Keep `/tasks` + docs say “Run” | Zero breaking change; matches M2 decision | Mild vocabulary dualism |
| Alias `/runs` now | Cleaner narrative | Extra surface, little Demo gain |
| Rename table/API | Pure naming | Migration cost, frontend churn, no capability gain |

**Policy:**  
- **External API:** keep `POST /tasks/{id}/cancel` and Task DTOs.  
- **Docs / Demo / README:** prefer “Agent Run” language.  
- **Internal:** optional type aliases / comments (`AnalysisTask` ≈ AgentRun).  
- **Hard rename:** only if M3+ introduces a non-BI Skill that makes “analysis_task” misleading.

### 3. Should timeout/cancel limits be explicit in architecture docs?

**Verdict: Yes — already in acceptance; promote to Charter/Contracts briefly.**

Must remain visible:

1. Timeout/cancel are **cooperative**; Worker records terminal status reliably.  
2. **No guarantee** of aborting in-flight LLM HTTP.  
3. **No guarantee** of interrupting DuckDB mid-query.  
4. Worker must **not** commit `succeeded` after `timed_out` / `cancelled`.  
5. Re-run = **create a new Run** (no auto-retry).

**Action (docs-only when convenient):** add a short “Run governance limitations” subsection under Platform Charter or Contracts — not a code change.

### 4. What stays deferred?

| Capability | Stay deferred? | Why |
|------------|----------------|-----|
| **Connector** | Yes as M2 follow-on product work; top M3 candidate | Highest Data-domain complementarity; highest complexity |
| **RBAC** | Companion only, not a phase theme | Creator/owner cancel already exists; invite/IAM out of scope |
| **Audit product** | Yes | steps + `failure_class` + platform traces suffice |
| **Second Skill** | Yes | Premature until Connector or a clear second domain exists |
| **Retry framework** | Yes | Explicitly rejected in M2 |

---

## Architecture boundary reminder (keep)

```text
Kernel     → Skill execution (data.bi)
Worker     → Run claim, timeout, cancel, failure_class, terminal writes
task_service / API → create, cancel, query
Product UI → minimal status + Cancel
```

Do not move lifecycle into Kernel unless a second runtime consumer appears.
