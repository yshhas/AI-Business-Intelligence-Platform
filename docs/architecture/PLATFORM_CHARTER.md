# Enterprise Data Agent Platform — Charter

**Document type:** Platform charter  
**Status:** Confirmed (Era 1 Foundation + Era 2 Capability frozen, 2026-07-22)  
**Foundation frozen:** M0–M3 boundaries  

**Eras**

| Era | Name | Phases |
|-----|------|--------|
| 1 | Platform Foundation | M0–M3 (**complete**) |
| 2 | Enterprise Capability Enhancement | M4+ ([roadmap](../archive/roadmap/ENTERPRISE_CAPABILITY_ROADMAP.md)) |

---

## 1. Official name

**Enterprise Data Agent Platform**

| Layer | Meaning |
|-------|---------|
| **Platform / Kernel** | Agent Runtime: `run`, skill registry, tools, policies, artifacts |
| **Skill** | Domain capability pack — first skill: **`data.bi`** (formerly “ChatBI”) |
| **Run Governance** | Worker / task lifecycle: timeout, cancel, `failure_class` (not Kernel) |
| **Data Plane** | Injected select executors behind Policy — today: **file→DuckDB** and **postgres_ro** |
| **Product shell** | Workspace / Dataset / Task / UI (FastAPI + React) |

**ChatBI is not the platform definition.** It is the first **Data Skill** (`data.bi`) running on this platform.

---

## 2. Relationship to RepoPilot

| | RepoPilot | This project |
|---|-----------|----------------|
| Role | **Engineering Agent** | **Enterprise Data Agent Platform** (Data Agent) |
| Domain | Code / Git / engineering change | Enterprise data analysis & data-plane policy |
| Shared idea | Governed Agent (tools, gates/policies, run honesty) | Same design *thought* |
| Boundary | Owns the code domain | **Does not implement a Code Agent in this repo** |

### Code-domain policy (precise wording)

- **Current strategy:** do not enter the code domain (avoid overlap with RepoPilot).
- **This repository:** does **not** implement a Code Agent.
- **Kernel:** remains **extensible** for future non-conflicting skills.
- **Anti-goal:** do not build a second RepoPilot here.

We do **not** use “never support code domain forever.” We use the statements above.

---

## 3. Proven narrative (M1–M3)

```text
Before:  ChatBI Application

After:   Enterprise Data Agent Platform
         ├── Kernel (Skill / Tool / Policy / Artifact)
         ├── Governed Run (timeout / cancel / failure_class)
         ├── Skill: data.bi
         └── Data Planes: file | postgres_ro
             (same Policy + Run governance)
```

| Phase | Proof |
|-------|--------|
| **M1** | Application → Platform + Skill |
| **M2** | Agent Run → Governed Runtime |
| **M3** | Data Agent → Governed Data Plane (thin RO Postgres; not Connector Framework) |

---

## 4. Non-goals

### Still out (unless an Era 2 phase explicitly opens a *thin* slice)

- Second business skill / Multi-Agent orchestration (Skill lifecycle trigger-gated)
- Code Agent / engineering tools in this repo
- **Connector Framework** / multi-source product / Catalog / schema crawler
- Write connectors / CDC / sync / ETL pipelines
- RAG knowledge base
- Standalone audit **microservice** as platform core (Traceable Execution ≠ SIEM product)
- Invite UI / enterprise IAM / full RBAC **suite** (thin resource ACL may open in M5)
- Heavy Tasks UI redesign / Run center product as a phase goal
- Pie charts, PDF export (unless a future phase explicitly opens them)

**In Foundation (M3):** single-env `POSTGRES_RO_DSN` + thin bind API + ≤2 `public.*` allowlisted tables.

---

## 5. Inheritance from ChatBI MVP

Kept as the `data.bi` execution path:

- PostgreSQL **platform** metadata, Redis queue, DuckDB analytics files
- Separate **enterprise data** Postgres (RO) for M3 Demo plane
- SQL Gate (Policy `sql.select_gate`) — plane-agnostic
- LangGraph pipeline (skill implementation)
- `result_json` compatibility for the product shell
- Worker + `run_analysis` Facade → `kernel.run(skill_id="data.bi")`

---

## 6. Architecture boundaries

```text
Product Shell
        |
Worker / Run Lifecycle
        |
Kernel.run
        |
Skill(data.bi)
        |
Tool(sql.execute_select)
        |
Policy(sql.select_gate)
        |
Data Plane executor (DuckDB | Postgres RO)
```

| Owns | Does not own |
|------|----------------|
| Kernel → Skill execution | Timeout / cancel / queue |
| Worker → Run terminals + `failure_class` | SQL Policy decisions |
| Policy → SELECT / allowlist before execute | Credentials vault / connector registry |
| Data Plane → engine-specific RO execute | Kernel registries |

---

## 7. Run governance limitations (M2 + M3)

Documented for Demo honesty:

- Timeout and cancel are **cooperative**. Terminal status (`timed_out` / `cancelled`) is recorded reliably by the Worker.
- There is **no guarantee** of immediately aborting in-flight LLM HTTP calls.
- There is **no guarantee** of interrupting an in-progress **DuckDB or Postgres** query.
- After `timed_out` / `cancelled`, the Worker must **not** persist a later `succeeded` outcome for that Run.
- Re-run means **create a new task/Run** — no automatic retry engine.
- Data-plane infra failures use `failure_class=connector_error` (distinct from `policy_denied` / `skill_error`).

---

## 8. Data Plane principles (M3)

- Access always goes through **Policy then executor** — no plane bypasses Gate.
- Credentials for RO plane live in **env** (`POSTGRES_RO_DSN`), never in Dataset plaintext or step payloads.
- Platform metadata DB and user data source DB stay **isolated**.
- Adding a plane means a new executor behind `execute_select`, **not** a Kernel Connector Registry.

---

## Related docs

- [PLATFORM_STORY_REVIEW.md](../archive/reviews/PLATFORM_STORY_REVIEW.md)  
- [PHASE_M3_RETROSPECTIVE.md](../archive/phase/PHASE_M3_RETROSPECTIVE.md)  
- [M4_VALUE_RANKING.md](../archive/roadmap/M4_VALUE_RANKING.md)  
- [PLATFORM_CONTRACTS.md](PLATFORM_CONTRACTS.md)
