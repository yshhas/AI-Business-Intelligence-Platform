# Phase M2 — Run Lifecycle Checklist（仅设计，待确认后编码）

**Status:** ✅ Implemented — see [PHASE_M2_ACCEPTANCE.md](PHASE_M2_ACCEPTANCE.md)
**Prerequisite:** M1 frozen (Enterprise Data Agent Platform + Skill `data.bi`)  
**Goal:** From “can run a Data Skill” → “can govern an Enterprise Agent Run”

**Narrative**
```text
M1: Skill runs on the platform
M2: Run is a first-class, governable runtime object
```

**Hard stop-lines**
- No new Skill / Connector / Multi-Agent / Audit service / large UI rewrite
- No Celery / full distributed job framework
- Keep Postgres + Redis List + single Worker process model
- Auth / Workspace / Dataset main flows unchanged (cancel may add a thin permission check later as companion, not IAM product)

---

## 1. Current Task / Worker state machine (as-is)

### 1.1 Status values today

| Status | Who sets | Meaning |
|--------|----------|---------|
| `pending` | API `create_task` | Row inserted; LPUSH to Redis |
| `running` | Worker on claim | `started_at` set |
| `succeeded` | Worker after runtime | `result_json` + `finished_at` |
| `failed` | Worker on exception; or enqueue failure in API | `error_message` + usually `finished_at` |

No: `cancelled`, `timed_out`, cancel flag, timeout deadline, failure class field.

### 1.2 Flow (as-is)

```text
POST /tasks
  → AnalysisTask(status=pending)
  → Redis LPUSH task_id
  → return task

Worker loop:
  BRPOP task_id
  → load task
  → if status ∉ {pending, running}: skip
  → pending → running (commit)
  → mock | agent runtime (blocking, unbounded wall time)
  → succeeded | failed
```

### 1.3 Gaps vs “governable Run”

| Gap | Effect |
|-----|--------|
| No timeout | LLM hang / stuck graph → task stays `running` forever |
| No cancel | User/API cannot stop a run |
| Opaque failures | Only free-text `error_message` |
| Re-queue / double consume | Same `task_id` re-LPUSH could re-enter if status still pending/running (weak idempotency) |
| Redis contract | Fire-and-forget List; no visibility timeout / ack |

### 1.4 What already helps M2

- Terminal timestamps: `started_at` / `finished_at`
- Steps retained on failure (Worker does not wipe steps on fail)
- Workspace-scoped GET task/steps (polling UI)
- M1 `result_json.platform` for skill/tool/policy traces

---

## 2. Target Run status model (to-be)

### 2.1 Naming

Product/API may keep resource path `/tasks` (compatibility).  
Platform vocabulary in docs + optional `result_json.platform.run` / fields: **Run**.

### 2.2 Status enum (M2)

| Status | Terminal? | Meaning |
|--------|-----------|---------|
| `pending` | No | Accepted, waiting for Worker |
| `running` | No | Claimed; Skill executing |
| `succeeded` | Yes | Completed with artifacts (or empty charts with limitations — same as today) |
| `failed` | Yes | Business/runtime failure (see failure class) |
| `cancelled` | Yes | Cancel requested and honored (or pending cancelled before start) |
| `timed_out` | Yes | Exceeded wall-clock budget while running |

**Rule:** Exactly one terminal state. Do not overload `failed` for cancel/timeout — separate statuses for Demo/narrative clarity.

### 2.3 Suggested columns (minimal schema evolution)

Prefer **additive** migration (no rename of `analysis_tasks`):

| Column | Type | Purpose |
|--------|------|---------|
| `cancel_requested` | bool, default false | Cooperative cancel flag |
| `failure_class` | str nullable | See §4 (only when terminal ≠ succeeded) |
| `timeout_seconds` | int nullable | Effective budget (copy from settings at create) |
| `attempt` | int default 1 | Idempotency / future retry (M2: mostly protection, not full retry engine) |

Optional JSON bump inside `result_json.platform.run`:
```json
{
  "run_id": "<task uuid>",
  "status": "timed_out",
  "failure_class": "timeout",
  "cancel_requested": false,
  "timeout_seconds": 120
}
```

### 2.4 Allowed transitions

```text
pending  → running | cancelled | failed(enqueue)
running  → succeeded | failed | cancelled | timed_out
```

Illegal: `succeeded` → anything; `cancelled` → `running`; etc.

---

## 3. Timeout / cancel — minimal implementation boundary

### 3.1 Timeout (must-have)

| Decision | M2 choice |
|----------|-----------|
| Scope | **Wall-clock from `started_at`** (or claim time) |
| Default | Config e.g. `RUN_TIMEOUT_SECONDS=120` (env) |
| Enforcement | **Worker-side** cooperative check + hard bound around Skill call |
| Granularity | Whole Run (not per-node) for M2 |

**Minimal mechanism (design options — pick one at coding kickoff):**

**Recommended (simplest, fits single Worker):**  
- Before/during Skill: run `kernel.run` / `run_analysis` in a **worker thread or process** with join timeout; on timeout → mark `timed_out`, set `failure_class=timeout`, best-effort stop (thread may not kill LLM HTTP instantly — document limitation).  
- **Also** periodic check: if `cancel_requested` or elapsed > budget → abort path.

**Alternative (lighter but weaker):**  
- Only check timeout **between** LangGraph nodes (requires Skill/kernel hooks). Better cooperativeness; more coupling to `data.bi`. Defer unless thread timeout proves too crude.

**Do not:** Distributed lease systems, multiple Worker fencing tokens (out of scope).

### 3.2 Cancel (must-have)

| API | `POST /api/v1/workspaces/{id}/tasks/{task_id}/cancel` |
|-----|--------------------------------------------------------|
| Auth | Workspace member; **prefer** creator or owner (thin companion check — not full RBAC product) |
| pending | Set `cancelled` immediately; Worker skips if dequeued later |
| running | Set `cancel_requested=true`; Worker observes and transitions to `cancelled` |
| terminal | 409 Conflict |

**Cooperative cancel:** Worker checks flag:
1. After dequeue / before Skill  
2. Ideally mid-run if using threaded runner + shared flag / between nodes later  

**Frontend (minimal):** one Cancel button on Analyze/Tasks when `pending|running` — no IA redesign.

### 3.3 Explicitly out of timeout/cancel MVP

- Killing in-flight HTTP to LLM with guaranteed abort  
- Cancel propagating into DuckDB query interrupt  
- Multi-Worker claim fencing  

Document as limitations in `result_json.limitations` / acceptance doc.

---

## 4. Failure classification design

### 4.1 Field: `failure_class`

Stable string enum (store on task row + echo in platform run block):

| Class | Typical status | Examples |
|-------|----------------|----------|
| `enqueue_error` | `failed` | Redis LPUSH failed |
| `policy_denied` | `failed` | SQL Gate / Policy reject exhausting retries or hard deny |
| `skill_error` | `failed` | Graph/LLM/runtime exception |
| `timeout` | `timed_out` | Wall clock exceeded |
| `cancelled` | `cancelled` | User/API cancel |
| `internal_error` | `failed` | Unexpected Worker/DB persistence errors |
| `unknown` | `failed` | Fallback |

Mapping guidance for Worker:
- `RuntimeError` containing `SQL Policy rejected` / Gate → `policy_denied`
- Timeout path → status `timed_out` + class `timeout`
- Cancel path → status `cancelled` + class `cancelled`
- Else → `skill_error` or `internal_error`

Keep `error_message` as human-readable detail (unchanged role).

### 4.2 Success path

`failure_class = null` when `succeeded`.

Enhancement-layer degrade (charts/report) still **succeeded** (M1 rule unchanged).

---

## 5. Redis / Worker contract — what changes?

### 5.1 Keep unchanged

| Piece | Keep |
|-------|------|
| Queue type | Redis **List** LPUSH / BRPOP |
| Payload | `task_id` UUID string only |
| Queue key | `ANALYSIS_QUEUE_KEY` |
| Single consumer loop | One Worker process (Demo scale) |

### 5.2 Soft contract additions (no new broker)

| Addition | Purpose |
|----------|---------|
| Worker skip rules | If status ∈ terminal OR (`pending` but already `cancelled`) → ack by skipping |
| Idempotent claim | Only `pending`→`running` if still `pending` (compare-and-set style update) |
| Optional re-queue policy | **M2 default: do not auto-retry**; manual “retry” = new task (simplest) |

### 5.3 Idempotency (裁剪版 — must-have lite)

| Scenario | Behavior |
|----------|----------|
| Same `task_id` dequeued twice | Second time: if already `succeeded/failed/cancelled/timed_out` → no-op; if `running` → skip or only continue if same Worker crash recovery **out of scope** |
| Duplicate POST create | Creates **new** Run (new id) — OK |
| `attempt` field | Default 1; full retry engine **deferred** |

**Retry engine:** optional stretch; default **out of M2 must-have**. If included later: only explicit `POST .../retry` creating new task or resetting with `attempt++` under strict rules — prefer **new task** to avoid state soup.

### 5.4 Kernel impact

- Prefer lifecycle in **Worker / task_service** (product shell + runtime ops).  
- Kernel `run()` stays synchronous Skill execution; timeout wraps the **call** to Facade/Kernel from Worker.  
- Avoid baking cancel into every Tool in M2 (unless cheap cooperative checks later).

---

## 6. Implementation steps (when coding starts)

| Step | Deliverable | Acceptance slice |
|------|-------------|------------------|
| **M2.0** | Spec freeze + config keys (`RUN_TIMEOUT_SECONDS`) | Doc only / already this file |
| **M2.1** | Migration: `cancel_requested`, `failure_class`, `timeout_seconds` (+ optional `attempt`) | Alembic upgrade |
| **M2.2** | Status transitions + claim CAS | Unit/smoke on transitions |
| **M2.3** | Timeout enforcement in Worker | Forced short timeout smoke → `timed_out` |
| **M2.4** | Cancel API + Worker honor flag | pending cancel + running cancel smokes |
| **M2.5** | Failure class mapping | Policy deny / skill error classified |
| **M2.6** | Schema/API Out fields + minimal Cancel button | Polling shows new statuses |
| **M2.7** | Acceptance doc + update PHASES | Real-env verify |

---

## 7. Acceptance criteria (Definition of Done)

- [ ] Run statuses include `cancelled` and `timed_out` as first-class terminals  
- [ ] Configurable timeout; exceeded run → `timed_out` + `failure_class=timeout`  
- [ ] `POST .../cancel` works for `pending` and cooperatively for `running`  
- [ ] Failures expose stable `failure_class` (not only free text)  
- [ ] Redis remains List-based; no Celery  
- [ ] Golden path still: upload → Analyze → SQL → table/chart/report → `succeeded`  
- [ ] M1 platform fields (`skill_id`, tools, policies) still present on success  
- [ ] Idempotent: terminal tasks are not re-executed if re-delivered  
- [ ] Frontend: status visible + Cancel for active runs (minimal)  
- [ ] Docs: limitations of cooperative cancel/timeout stated  

---

## 8. Explicit non-goals (M2)

| Do not |
|--------|
| New Skill / second graph |
| Connector / external DB |
| Multi-Agent / second orchestrator |
| Standalone Audit service or audit tables |
| Large Tasks IA redesign / Run center product |
| Celery / RQ / Kafka |
| Full retry/idempotency framework (saga, exactly-once) |
| Invite / enterprise IAM UI |
| Guaranteed kill of LLM HTTP or DuckDB mid-query |

---

## 9. Open points for confirmation before coding

1. **Timeout default:** 120s vs 180s?  
2. **Timeout mechanism:** thread+join (recommended) vs between-node hooks only?  
3. **Cancel permission:** any workspace member vs creator/owner only?  
4. **Retry:** confirm **out of scope** (new task only) for M2?  
5. **API naming:** keep `/tasks/.../cancel` vs also alias `/runs/...`? (recommend keep `/tasks`)

---

## 10. One-line summary

> M2 makes **Run** governable: bounded time, cancellable, classified failures, light idempotent claim — without turning the stack into a distributed job platform or reopening M1 stop-lines.
