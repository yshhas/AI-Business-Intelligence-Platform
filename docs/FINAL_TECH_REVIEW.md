# Final CTO Technical Review & Project Freeze

**Product:** Enterprise Data Agent Platform  
**Document type:** Final architecture & capability freeze review  
**Status:** Frozen for this engineering arc (Era 1–2 + Era 3 P0/DH + AI engineering fusion T-01…T-13)  
**Audience:** CTO / hiring bar / technical interview portfolio  
**Rule:** Describes **what is implemented**. Does not authorize new features.

---

## Executive verdict

This repository is a **governed Enterprise Data Agent Platform**, not a ChatBI toy, not a second RepoPilot, and not a generic “LLM app.”

The durable claim:

> Product Shell enqueues a **Run** → Worker governs lifecycle → **Kernel** dispatches **Skill `data.bi`** → fixed **LangGraph** pipeline → **Policy** (`sql.select_gate`) → **Data Plane** (DuckDB | Postgres RO) → **Trace / Artifacts** remain the execution truth.

AI-engineering work (LLM client, retry, JSON mode, prompt defense, usage on Trace, SSE progress, Skill lifecycle lite, Docker, CI) **strengthened the existing spine**. It did **not** replace Kernel, Worker, or Policy with RAG / ReAct / Multi-Agent fashion.

**Freeze posture:** stop feature expansion on this arc; next work only via explicit roadmap slices that preserve the spine.

---

## 1. Final architecture

```text
Frontend (React + Vite)
        │  REST + SSE (task progress)
        ▼
FastAPI Product Shell
  auth · workspace · dataset · task · artifacts · health
        │
        ├── Task / SSE / Execution Trace  (read models over DB)
        │
        ▼
Redis List queue  ──►  Analysis Worker
                        timeout · cancel · capacity · reclaim
                        │
                        ▼
                   Kernel.run(skill_id="data.bi")
                        │
                        ▼
                   Skill: data.bi
                        │
                        ▼
                   LangGraph fixed pipeline
                   (SQL → Gate → Execute → Charts → Report)
                        │
                        ▼
                   Policy: sql.select_gate
                        │
                        ▼
                   Data Plane
                   ├── file → DuckDB
                   └── postgres_ro (SELECT-only)
```

### Layer responsibilities

| Layer | Responsibility | What it is *not* |
|-------|----------------|------------------|
| **Frontend** | Workspace UX: upload, Analyze, steps/progress, Trace/Artifacts panels | Not a chat product; SSE is **task progress**, not token theatre |
| **FastAPI Shell** | Auth, tenancy edges, Dataset/Task APIs, enqueue gates, SSE watch, readiness | Not the Agent brain; no LangGraph inside HTTP handlers |
| **Task / SSE / Trace** | Run status, step timeline, Execution Trace, Artifact metadata | Not an event store; SSE polls Task/Steps (existing DB) |
| **Redis Worker** | Async Run governance: claim, heartbeat, timeout, cancel, in-flight/queue caps | Not Celery/Kafka; not Kernel |
| **Kernel** | `run(skill_id)`, registry of Skill/Tool/Policy/Artifact contracts | Not a free-form planner; not Multi-Agent bus |
| **Skill `data.bi`** | Domain pack: Text-to-SQL → table/chart/report | First skill only — not a marketplace |
| **LangGraph pipeline** | **Fixed** node graph for `data.bi` | Not ReAct loops; not dynamic tool choice |
| **Policy Gate** | Plane-agnostic SQL allow/deny (`sql.select_gate`) before execute | Not ABAC suite / policy-as-code product |
| **Data Plane** | Injected SELECT executors after Policy | Not ETL / CDC / Connector Framework |

### Spine invariants (do not overturn)

1. **Run honesty** > chat fluency (timeout / cancel / `failure_class` are first-class).  
2. **Policy before Data Plane** — no “LLM said so → execute.”  
3. **Trace is truth**; logs/SSE are operator/UX correlation.  
4. **One Skill proven** (`data.bi`) before Multi-Skill theatre.  
5. **RepoPilot owns code domain**; this repo does not grow a Code Agent.

---

## 2. Technical asset inventory

Completeness: **Complete** = production-shaped for Demo/ops of this arc · **Solid** = correct and gated · **Lite** = intentionally thin slice.

### Platform foundation (Era 1–2)

| Capability | Location (primary) | Degree | Design value |
|------------|-------------------|--------|--------------|
| Kernel runtime + registry | `agent/kernel/runtime.py`, `registry.py`, `types.py` | Complete | Makes “platform vs app” real |
| Skill `data.bi` | `agent/skills/data_bi/` | Complete | First governed Data Skill |
| LangGraph pipeline | `agent/graph.py`, `agent/nodes/pipeline.py` | Complete | Deterministic skill path |
| SQL Policy gate | `agent/gates/sql_gate.py`, kernel policies | Complete | Governance proof |
| Data planes | DuckDB services · `postgres_ro` bind/exec | Complete | Same Policy, two planes |
| Worker lifecycle | `backend/app/workers/analysis_worker.py`, `run_lifecycle.py` | Complete | Timeout / cancel / failure_class |
| Capacity / reclaim | `runtime_essentials.py`, E3 settings | Solid | Demo honesty under load |
| Execution Trace | `execution_trace.py`, task execution API | Complete | Audit-shaped Run story (≠ SIEM) |
| Thin permissions | workspace + role ACL (M5) | Solid | Enough Shell governance |
| Artifacts | `run_artifacts`, artifact service (M6) | Complete | First-class outputs + lineage |

### AI engineering fusion (this arc)

| Capability | Location | Degree | Design value |
|------------|----------|--------|--------------|
| **Dep pin (Web stack)** | `backend/requirements.txt` | Complete | Reproducible install / Docker / CI |
| **LLM Client** | `agent/llm_client.py` · facade `agent/llm.py` | Complete | Typed errors; transport injectable; pipeline stays thin |
| **Retry** | `LLMClient.chat` + `LLM_MAX_RETRIES*` settings | Solid | Only timeout/transport/429/5xx; preserves final exception type |
| **JSON Mode + Schema** | `response_format=json_object` · `agent/schemas_llm.py` (`SqlDraft`) | Complete | Structured SQL draft; legacy text fallback for resilience |
| **Prompt few-shot + injection defense** | `agent/prompts_sql.py` | Solid | Delimiters + untrusted-user rules; few-shot JSON examples |
| **LLM usage → Trace** | `LLMCallResult` / `as_step_llm()` → step `output_json.llm` | Solid | Cost/latency visibility without hidden CoT dump |
| **Request ID + JSON logs** | `app/core/observability.py`, `middleware/request_id.py` | Solid | Correlate API ↔ Worker ↔ Trace |
| **Skill Lifecycle lite** | `skill_lifecycle.py`, registry meta, `skill_version` on Run | Lite→Solid | Enable/disable + version pin; **no** marketplace |
| **SSE Task Events** | `task_events.py`, `GET .../tasks/{id}/events`, Analyze SSE client | Solid | Progress UX; **not** token streaming |
| **Docker API/Worker** | `docker/Dockerfile`, `entrypoint.py`, compose `api`/`worker` | Solid | One-command Demo stack |
| **CI Release Gate** | `.github/workflows/ci.yml` → `smoke_release_gate.py` | Solid | Automates existing gate; **not** CD |

### Product shell & ops

| Capability | Location | Degree | Design value |
|------------|----------|--------|--------------|
| React workbench | `frontend/src/**` | Solid | Shell for Demo narrative |
| Health live/ready | `routes_health.py` | Solid | DB+Redis readiness |
| Ops docs / config matrix | `docs/OPS_RUNBOOK.md`, `OPS_CONFIG_MATRIX.md` | Solid | Operator repeatability |
| Release smokes | `backend/scripts/smoke_*.py`, `smoke_release_gate.py` | Complete | Regression contract |

---

## 3. Won't Do (explicit)

| Won't Do | Why |
|----------|-----|
| **RAG** | This product answers **governed SQL over bound data planes**, not “retrieve chunks from a corpus.” RAG would redefine the product as a knowledge chatbot and dilute Policy/Data Plane proof. |
| **Embedding / Vector DB** | No retrieval index in the architecture; adds infra and identity drift without helping Text-to-SQL governance. |
| **Generic ReAct Agent** | Conflicts with **fixed Skill graph + Policy-before-execute**. Free tool loops undermine Run honesty and allowlist discipline. |
| **Multi-Agent** | One Skill is the proof. Multi-Agent orchestration is theatre until a second Skill and lifecycle rules are justified. |
| **Code Agent / Git / Patch (RepoPilot migration)** | **Domain collision.** RepoPilot owns engineering change; this platform owns enterprise data analysis. Fusion would create a confused second RepoPilot. |
| **WebSocket** | SSE covers Analyze progress; WebSocket adds protocol complexity without a second realtime product surface. |
| **Token streaming / ChatGPT-style output** | UX goal is **Run progress**, not token theatre; streaming invites leaking intermediate/hidden reasoning. |
| **LangSmith dual-track tracing** | Execution Trace on the Run is the product truth. Vendor dual pipelines increase cost/coupling without changing governance. |
| **LLM response cache** | Wrong layer for correctness-sensitive SQL generation; risk of stale/wrong SQL under schema or prompt change. Prefer Trace + usage metrics first. |
| **Celery / new broker / Event Store** | Redis List Worker is intentional and sufficient for Demo-scale governed Runs. |
| **K8s / Helm / Terraform / cloud CD** | Ops arc stopped at Compose + CI gate. Deploy platforms are a different program. |
| **Connector Framework / Catalog / ETL** | Explicitly deferred; M3 proved **thin RO plane**, not a connector product. |
| **Full IAM / SIEM / Report CMS** | Thin Shell ACL + Run Trace are enough for this identity; suite products are gravity wells. |

**Decision rule:** if a shiny AI pattern does not strengthen **Skill → Policy → Plane → Trace**, it stays out.

---

## 4. RepoPilot boundary

| Dimension | This project | RepoPilot |
|-----------|--------------|-----------|
| **Role** | Enterprise **Data** Agent Platform | **Engineering** Agent |
| **Object of work** | Datasets, SQL, charts, reports, policy-gated planes | Repos, diffs, patches, engineering change |
| **Governance proof** | `sql.select_gate`, Run timeout/cancel, Trace/Artifacts | Code-domain tools, gates, run honesty in *that* domain |
| **Shared idea** | Governed Agent (tools, policies, honest Runs) | Same *design thought* |
| **Repo policy** | Does **not** implement Code Agent | Owns code domain |

### What stays here

- Kernel / Skill / Policy / Data Plane / Worker / Trace / Artifact  
- `data.bi` Text-to-SQL path and Shell (Workspace / Dataset / Task)  
- LLM engineering that serves **SQL skill quality & operability**

### What stays in RepoPilot

- Git / patch / code-edit agent loops  
- Engineering-tool catalogs and code-domain workflows  

### Why not fuse

1. **Different truth objects** (tables vs trees).  
2. **Different failure classes and policies** (SQL allowlists vs code change risk).  
3. **Narrative clarity:** one resume story = Data Agent Platform; merging creates “AI everything” mush.  
4. **Anti-goal:** do not build a second RepoPilot inside this monorepo.

Kernel remains *conceptually* extensible for future **non-conflicting** skills — that is not a license to import RepoPilot.

---

## 5. Production-readiness assessment

Scores are **honest for this Demo / portfolio / operable platform**, not “Fortune-500 multi-region SaaS.”

Scale: **1** fragile · **3** Demo-solid · **5** enterprise-hardened.

| Dimension | Score | Evidence | Shortfall (do not inflate) |
|-----------|-------|----------|----------------------------|
| **Architecture** | **4.5** | Clear spine; Kernel/Skill/Policy/Plane separation proven (M1–M6) | Single primary Skill; no Connector Framework |
| **Security** | **3.5** | SQL gate, RO role, prompt delimiters, JWT + workspace roles, no CoT dump on SSE | Not enterprise IAM/SSO; injection defense is prompt-layer, not a full LLM firewall; secrets via env only |
| **Reliability** | **3.5** | Timeout/cancel/failure_class, retries on LLM transport, capacity caps, reclaim | Single-region Compose; no multi-AZ story; heuristic SQL escape hatch for Demo |
| **Observability** | **3.5** | Request ID, JSON logs, Trace + LLM usage on steps, health ready | No APM/SIEM; Worker has no HTTP health; metrics are log/Trace-centric |
| **Deployment** | **4.0** | Compose API+Worker+deps; runbook; CI release gate | Not K8s; host port conflicts possible; frontend still host-side |
| **Scalability** | **2.5** | Global in-flight + queue depth; one worker pattern documented | Not horizontal multi-tenant scale; DuckDB/file plane is local-volume shaped |

**Overall:** **strong architecture identity**, **operable Demo**, **intentionally incomplete** as a hyperscale SaaS. That gap is a **choice**, not an accident.

---

## 6. Next-phase roadmap (only what is real)

Authorize nothing here — these are **candidates** that fit the platform identity. Do **not** reopen Won't Do.

| Priority theme | Thin intent | Why it belongs |
|----------------|-------------|----------------|
| **Second Skill (gated)** | Only after lifecycle discipline is real | Proves platform ≠ single app; still no Multi-Agent mashup |
| **Connector Framework (thin)** | More governed planes behind **same** Policy | Extends Data Agent story without ETL religion |
| **Permission model +** | Resource ACL depth where Demo pain appears | Shell governance, not full IAM suite |
| **Data governance lite** | Stronger allowlists, schema/contract honesty on Trace | Deepens Policy/Plane trust |
| **Cost control** | Budgets/alerts from existing LLM usage on Trace | Uses assets already shipped (T-07) |
| **Evaluation framework** | Golden questions / SQL-gate fixtures / regression sets | Makes LLM changes falsifiable without LangSmith dual stack |
| **Policy Trace enrichment** | Richer `PolicyDecision` context on Trace | Opportunistic; not a new “Policy Engine” product |
| **Ops evidence-driven only** | Workspace caps / `replay_of` if multi-tenant pain shows | Avoid Runtime theatre without evidence |

**Still deferred / refuse by default:** RAG, ReAct, Multi-Agent mesh, Code Agent, WebSocket token chat, cloud CD platforms.

---

## 7. Freeze checklist

| Item | State |
|------|-------|
| Era 1 (M0–M3) | Frozen |
| Era 2 (M4–M6) | Frozen |
| Era 3 Runtime P0 + Deployment Hygiene | Frozen |
| AI engineering fusion T-01…T-13 (excl. skipped T-IDs) | **Accepted / freeze this arc** |
| Charter spine | Unchanged |
| Won't Do list | Binding for this review |
| Next coding | **Requires new explicit phase authorization** |

### Operator pointers

- Runbook: [`OPS_RUNBOOK.md`](./OPS_RUNBOOK.md)  
- Compose: [`../docker/README.md`](../docker/README.md)  
- CI: [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml)  
- Charter: [`PLATFORM_CHARTER.md`](./PLATFORM_CHARTER.md)  
- Release gate: `backend/scripts/smoke_release_gate.py`

---

## Closing statement

The project’s value is **architectural honesty**:

- A **Data Agent Platform** with a real Kernel and one proven Skill  
- **Policy in front of data**  
- **Governed Runs** instead of chat sessions  
- Engineering upgrades that make LLM calls **operable and traceable**  
- A hard boundary against RepoPilot and against AI-feature gravity wells  

That is sufficient to freeze this arc. Further work must be a **thin, authorized slice** on the same spine — not a redesign.

**End of Final CTO Technical Review.**
