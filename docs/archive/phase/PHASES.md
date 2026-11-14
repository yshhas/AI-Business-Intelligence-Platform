# Phase checklist

MVP scope is **frozen**. Do not pull Phase 3+ work into Phase 0–2.

## Phase 0 — Skeleton

- [x] Done (see PHASE0_CHECKLIST.md)

## Phase 1 — Auth + Workspace

- [x] Migrations: users / workspaces / workspace_members
- [x] Password hash/verify + JWT create/decode
- [x] Register (user + default workspace + owner) + login + `/me`
- [x] Workspace list / detail / rename
- [x] Frontend login/register + auth guard + **Dashboard** (`/app`)
- [x] Dialect abstraction for future Postgres switch (`db_dialect.py`)

**Acceptance:** register → JWT → workspace → Dashboard; refresh keeps session; logout clears it.

**Forbidden still:** datasets, DuckDB upload, tasks, LangGraph, Redis consumers.

**DB policy:** Phase 1 now runs on **PostgreSQL** via Compose (`localhost:5433`). SQLite file may remain as historical smoke data only. See `PHASE1_POSTGRES_SWITCH.md`.

## Phase 2 — Upload + DuckDB

- [x] Storage paths + `datasets` migration
- [x] `duckdb_service` + `dataset_service` + upload/list/preview APIs
- [x] Frontend Datasets page
- [x] **Final acceptance** — see `PHASE2_ACCEPTANCE.md`（冻结）

**Forbidden still:** LangGraph, Agent, NL/Text-to-SQL, reports, charts.

## Phase 3 — Async task skeleton

- [x] Redis queue + `analysis_tasks` / `agent_run_steps`
- [x] Worker mock runtime (`ANALYSIS_RUNTIME=mock`)
- [x] Task APIs + Analyze/Tasks polling UI
- [x] See `PHASE3_CHECKLIST.md`

**Forbidden still:** LangGraph, LLM, Text-to-SQL, reports, charts, real Agent.

## Phase 4 — Text-to-SQL slim LangGraph

- [x] SQL Gate + `run_select`
- [x] Agent runtime + Worker `mock|agent`
- [x] See `PHASE4_CHECKLIST.md` / `PHASE4_ACCEPTANCE.md`（冻结）

## Phase 5 — Charts + short report

- [x] ChartSpec (`bar`|`line`) heuristic + report markdown
- [x] Graph nodes `build_charts` / `write_report`
- [x] Frontend render charts + report
- [x] See `PHASE5_CHECKLIST.md` / `PHASE5_ACCEPTANCE.md`

**Forbidden still:** multi-agent, pie charts (deferred), new task tables, PDF export.

---

## Migration track — Enterprise Data Agent Platform

Strategic rename: ChatBI MVP becomes Skill **`data.bi`** on **Enterprise Data Agent Platform**.  
See [PLATFORM_CHARTER.md](../../architecture/PLATFORM_CHARTER.md).

### Phase M0 — Charter + contracts (design)

- [x] Platform charter + frozen contracts
- [x] See `PHASE_M0_CHECKLIST.md`, `PLATFORM_CONTRACTS.md`

### Phase M1 — Kernel + data.bi (architecture, no new domain)

- [x] Kernel / Skill / Tool / Policy / Artifact / Run
- [x] Facade `run_analysis` → `kernel.run("data.bi")`
- [x] Real-env E2E + policy-before-DuckDB verified
- [x] **Frozen** — see `PHASE_M1_ACCEPTANCE.md` / `PHASE_M1_RETROSPECTIVE.md`

**M1 stop-line:** no second skill, no Code Agent, no connector framework, no audit product, no Tasks UI rewrite.

### Phase M2 — Run lifecycle

- [x] timeout / cancel / failure_class
- [x] Redis List Worker retained; no Celery; no auto-retry
- [x] Real smoke verified
- [x] **Frozen** — see `PHASE_M2_ACCEPTANCE.md` / `PHASE_M2_RETROSPECTIVE.md`

### Phase M3 — Connector thin slice (Governed Data Plane)

- [x] Postgres read-only behind `execute_select` + Policy
- [x] Same Runtime / Policy / Run governance on second data plane
- [x] Real smoke verified (`smoke_m3_connector.py`)
- [x] **Frozen** — see `PHASE_M3_ACCEPTANCE.md` / `PHASE_M3_RETROSPECTIVE.md`

**M3 stop-line:** no Connector Framework, no Catalog/ETL/writes, no second Skill.

### Phase M4 — Traceable Execution Model

- [x] `to_execution_trace()` + `platform.execution` materialization
- [x] Denormalized filters: skill_id / source_type / policy_denied
- [x] `GET /tasks/{id}/execution` + list filters
- [x] Minimal Run Trace UI (no Audit Center)
- [x] Smoke: `smoke_m4_execution_trace.py`
- [x] **Frozen** — see `PHASE_M4_ACCEPTANCE.md` / `PHASE_M4_RETROSPECTIVE.md`

### Phase M5 — Resource Permission (thin RBAC)

- [x] Central `permissions.py` matrix (workspace + role)
- [x] viewer: read Dataset/Run/Trace; no upload/bind/Analyze
- [x] owner/analyst: golden path + postgres_ro bind/use
- [x] 403 in-workspace / 404 cross-workspace (membership)
- [x] Smoke: `smoke_m5_permissions.py`
- [x] **Frozen** — see `PHASE_M5_ACCEPTANCE.md` / `PHASE_M5_RETROSPECTIVE.md`

### Phase M6 — Artifact Lifecycle

- [x] Thin `run_artifacts` table (metadata + content_ref; UUID ids)
- [x] Skill assigns UUID; Worker materializes; Trace refs synced
- [x] `GET /tasks/{id}/artifacts` + get-by-id (run-scoped only)
- [x] Status `available` \| `unavailable` (+ stubs on partial)
- [x] M5 permission inherit (`artifact.list` / `artifact.get`)
- [x] Minimal Artifacts UI on Analyze / Tasks
- [x] Smoke: `smoke_m6_artifacts.py`
- [x] **Frozen** — see `PHASE_M6_ACCEPTANCE.md` / `PHASE_M6_RETROSPECTIVE.md`

**M6 stop-line:** no Report Center / CMS / PDF / Artifact microservice / retention system.

---

### Phase E3 — Runtime Essentials (Era 3 P0)

- [x] Stale `running` reclaim → `failed` / `runtime_reclaimed`
- [x] Global in-flight limit (enqueue 429 + claim defer)
- [x] Queue depth enqueue guard (Redis List `LLEN`)
- [x] Optional heartbeat freshness (`last_heartbeat_at`) — not a lease
- [x] Smoke: `smoke_e3_runtime_essentials.py`
- [x] **Frozen** — see `PHASE_E3_RUNTIME_ESSENTIALS_ACCEPTANCE.md` / `PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md`

**E3 stop-line:** no auto-retry/resume, no Celery/Streams, no workspace cap / replay_of in P0.

---

### Phase E3b — Deployment Hygiene

- [x] Config matrix + `.env.example` (`OPS_CONFIG_MATRIX.md`)
- [x] `/health/live` · `/health/ready` (DB + Redis)
- [x] `smoke_release_gate.py` (M3 conditional)
- [x] Operator runbook (`OPS_RUNBOOK.md`)
- [x] Trace-aligned structured logs
- [x] **Frozen** — see `PHASE_E3_DEPLOYMENT_HYGIENE_ACCEPTANCE.md` / `PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md`

**DH stop-line:** no APM/SIEM, no Worker HTTP, no Dockerfile/Actions in v1, no Runtime reopen.

---

## Era status

| Era | Scope | Status |
|-----|-------|--------|
| **Era 1** | M0–M3 Platform Foundation | ✅ Frozen |
| **Era 2** | M4–M6 Enterprise Capability | ✅ Frozen |
| **Era 3 P0** | Runtime Essentials | ✅ Frozen |
| **Era 3 DH** | Deployment Hygiene | ✅ Frozen |
| **P0-1** | Evaluation Framework (core golden + CI gate) | ✅ **Frozen** — [ACCEPTANCE](PHASE_P0_1_EVALUATION_ACCEPTANCE.md) |
| **P0-2** | Soft Cost Budget (workspace UTC-day) | ✅ **Frozen** — [ACCEPTANCE](PHASE_P0_2_COST_BUDGET_ACCEPTANCE.md) |
| **P1** | Permission / Governance (Dataset ACL + Trace authz) | ✅ **Complete** — [ACCEPTANCE](PHASE_P1_PERMISSION_ACCEPTANCE.md) |
| **E1-AC** | Schema Linking Lite + Eval Quality | ✅ **Frozen** — [FINAL_STATUS](PHASE_E1_AC_FINAL_STATUS.md) · [ACCEPTANCE](PHASE_E1_AC_ACCEPTANCE.md) |
| **E1-B** | SQL Repair | ⏸ Evidence-gated — not started |
| **E2** | Trace / Analyze Explainability | ✅ **Frozen** — [FINAL_STATUS](PHASE_E2_FINAL_STATUS.md) · [ACCEPTANCE](PHASE_E2_ACCEPTANCE.md) |

**Next:** **Release v1.0 Feature Freeze** — [FINAL_RELEASE.md](../../FINAL_RELEASE.md) · [RESUME_HIGHLIGHTS.md](../interview/RESUME_HIGHLIGHTS.md) · [INTERVIEW_GUIDE.md](../interview/INTERVIEW_GUIDE.md).  
**Wave 4** (single-cloud IaC) remains **Pending** — do not start without explicit authorization.  
Hold: no RAG / ReAct / Multi-Agent / Connector Framework / Celery without evidence · **no code changes without new requirements**.

### Wave 3 / P2 Platform Proof — ✅ Done

| Item | Doc |
|------|-----|
| Second Skill `data.profile` | [SKILL_DATA_PROFILE_CHARTER.md](../../architecture/SKILL_DATA_PROFILE_CHARTER.md) |
| Thin Plane + optional MySQL RO | [DATA_PLANE.md](../../architecture/DATA_PLANE.md) |
| Workspace Memory | [WORKSPACE_MEMORY.md](../../design/WORKSPACE_MEMORY.md) |
| OIDC MVP | [OIDC.md](../../design/OIDC.md) |
| MCP read-only HTTP | [MCP.md](../../design/MCP.md) |
| ACL→allowlist · Idempotency · Guardrails | `project_upgrade_plan.md` Wave 3 |

See [ERA_1_ERA_2_SUMMARY.md](../era/ERA_1_ERA_2_SUMMARY.md) · [OPS_RUNBOOK.md](../../ops/OPS_RUNBOOK.md) · [evals/README.md](../../../evals/README.md) · [project_upgrade_plan.md](../roadmap/project_upgrade_plan.md).

