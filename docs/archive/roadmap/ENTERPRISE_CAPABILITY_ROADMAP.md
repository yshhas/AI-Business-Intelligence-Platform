# Enterprise Capability Roadmap

**Status:** ✅ **Era 2 (M4–M6) delivered & frozen** (2026-07-22)  
**Supersedes:** long-term “Stable freeze only” as the *default end state*  
**Does not reopen:** M1–M3 Kernel / Skill / Policy / Run / Data Plane **boundaries**  
**Close-out:** [ERA_1_ERA_2_SUMMARY.md](../era/ERA_1_ERA_2_SUMMARY.md)

---

## 0. Strategic reframing

| Era | Name | Scope | Status |
|-----|------|-------|--------|
| **Era 1** | **Platform Foundation** | M0–M3 | ✅ **Complete / frozen** |
| **Era 2** | **Enterprise Capability Enhancement** | M4–M6 | ✅ **Complete / frozen** |

### Era 1 proved (do not rebuild)

```text
Skill execution
    → Policy governed
    → Run lifecycle managed
    → Multiple data planes
```

Assets to **extend**, not replace:

| Asset | Location / form |
|-------|-----------------|
| Kernel `run` + registries | `agent/kernel` |
| Skill `data.bi` | LangGraph adapter |
| Policy `sql.select_gate` | Gate + Tool wrap |
| Run terminals + `failure_class` | Worker / `analysis_tasks` |
| Steps + tool/policy enrichment | `agent_run_steps` + `result_json.platform` |
| Data planes | `file` / `postgres_ro` behind `execute_select` |

### Era 2 goal (achieved)

> 在不推翻 Foundation 边界的前提下，补齐 **Enterprise Agent** 必需的可追溯、可授权、可治理产出 —— 而不是扩成 BI/ETL/IAM 套件。

Claim upgrade path:

```text
Foundation:  “可治理的 Data Agent Runtime（可 Demo）”
Capability:  “可上企业叙事的 Data Agent Platform（可审计 · 可授权 · 产出可管）”
```

**Delivered chain:**

```text
M4 Trace → M5 Permission → M6 Artifact Entity
```

---

## 1. Architecture invariants (Era 2 must keep)

```text
Product Shell
        |
Worker / Run Lifecycle          ← may gain observability hooks; still owns timeout/cancel
        |
Kernel.run                      ← still Skill dispatch only
        |
Skill(data.bi)                  ← still first Skill; no forced second Skill
        |
Tool → Policy → Data Plane
```

| Allowed in Era 2 | Forbidden (overbuild / boundary break) |
|------------------|----------------------------------------|
| Query/export/index of existing Run/step/policy traces | New “Audit microservice” as identity of the platform |
| Resource checks on Dataset / Run / bind / plane | Full IAM, SSO product, invite org suite |
| Artifact retention / lineage metadata | PDF factory, Chart marketplace, BI authoring IDE |
| Selective runtime budgets / better failure taxonomy | Celery, distributed saga, guaranteed kill of LLM/DB |
| Skill **version label** / enable flag (thin) | Skill store, multi-agent mesh, hot-plugin marketplace |
| Extend `execute_select` planes only with Policy-first | Connector Framework / Catalog / ETL / writes |

---

## 2. Capability gap analysis (vs Foundation)

### 2.1 Audit / Observability

| | |
|--|--|
| **Have** | `agent_run_steps`, tool_id/policy_id enrichment, `platform.run`, `failure_class`, `data_plane` echo |
| **Gap** | Traces are **append-only side effects**, not a **first-class queryable execution model**; hard to answer “who ran what, under which policy, on which plane, with what denial?” across Runs |
| **Enterprise need** | **Essential** — “Agent 可追溯” is table stakes next to RepoPilot’s governance story |
| **Overbuild** | SIEM product, immutable WORM store, separate audit DB service, real-time anomaly ML |
| **M4 posture** | Build **Traceable Execution Model** on existing steps/platform — not a Demo badge |

### 2.2 Resource-level Permission / RBAC

| | |
|--|--|
| **Have** | Workspace membership; owner/analyst/viewer roles; cancel creator\|owner; postgres bind/run companion |
| **Gap** | No consistent **resource ACL** on Dataset / Run / Data-plane bind; viewer vs analyst semantics uneven |
| **Enterprise need** | **Essential (thin)** — once multiple planes + audit exist, authorization must be explainable |
| **Overbuild** | Org trees, invite flows, ABAC engine, policy-as-code IAM, SCIM |
| **Fit after Audit** | Permissions without traces are hard to Demo; traces without permissions are incomplete enterprise |

### 2.3 Artifact lifecycle

| | |
|--|--|
| **Have** | Artifact types in RunResult; projection to `result_json`; charts/report as Skill outputs |
| **Gap** | Artifacts die inside the Run blob — no retention policy, stable artifact id across API, “approved output” state |
| **Enterprise need** | **Important, not first** — pairs with audit (“this report is the governed output of Run X”) |
| **Overbuild** | Document CMS, digital signatures product, multi-format export farm, collaborative editing |
| **Note** | Must stay **platform output governance**, not ChatBI feature race |

### 2.4 Skill lifecycle

| | |
|--|--|
| **Have** | In-memory registry; single Skill `data.bi`; Facade skill_id |
| **Gap** | No version pin on Run, no disable/deprecate, no multi-skill ops |
| **Enterprise need** | **Latent** — becomes essential when a **second Skill** exists |
| **Overbuild** | Doing full Skill Ops / plugin market with one Skill |
| **Trigger** | Explicit second domain Skill decision — until then, at most a version string on Run |

### 2.5 Runtime advanced governance

| | |
|--|--|
| **Have** | Cooperative timeout/cancel; `failure_class`; no auto-retry; Redis List worker |
| **Gap** | No cost/token budget, no per-workspace concurrency cap, weak interrupt of in-flight work, limited SLO signals |
| **Enterprise need** | **Selective** — budgets/concurrency are enterprise-real; “distributed job platform” is not |
| **Overbuild** | Celery/Kafka rewrite, exactly-once saga, guaranteed LLM/DB kill, multi-region failover |
| **Fit** | After Audit (measure then constrain) or thin companion inside later Ms |

---

## 3. Essential vs overbuild (summary)

| Capability | Enterprise Platform? | Verdict |
|------------|----------------------|---------|
| Traceable execution model (Audit/Obs) | **Required next** | Build thin, queryable, Run-centric |
| Resource permission on Dataset/Run/Plane | **Required soon** | Thin ACL; no IAM suite |
| Artifact identity + retention lite | **Should have** | After traces exist |
| Runtime budgets / concurrency | **Nice → should** | Selective controls only |
| Skill version pin on Run | **Nice** | One field OK early; full lifecycle deferred |
| Skill marketplace / second Skill ops | **Overbuild now** | Trigger-gated |
| Connector Framework / Catalog / ETL | **Out (Era 2)** | Foundation already proved planes |
| Standalone Audit microservice | **Overbuild** | Prefer extend steps + query API |
| Multi-Agent orchestration | **Out** | Not this era’s thesis |

---

## 4. Era 2 phase map (M4 / M5 / M6)

See detailed scores: [ENTERPRISE_M4_M6_RANKING.md](ENTERPRISE_M4_M6_RANKING.md)

```text
Era 1 Foundation (done)
        │
        ▼
M4  Traceable Execution (Audit / Observability)
        │
        ▼
M5  Resource Authorization (thin RBAC on resources)
        │
        ▼
M6  Artifact Lifecycle lite  (+ optional Runtime budget companion)
        │
        ▼
Later (trigger-gated): Skill lifecycle · Runtime advanced · second Skill
```

**Design rule:** each M ships a **checklist → acceptance → freeze** like M1–M3; Foundation boundaries stay frozen.

---

## 5. Relationship to RepoPilot (Era 2)

| Shared theme | RepoPilot | This platform (Era 2 target) |
|--------------|-----------|------------------------------|
| Traceability | Engineering change / agent traces | Data Agent Run / Tool / Policy / Plane traces |
| Authorization | Repo/workspace engineering perms | Dataset / Run / data-plane perms |
| Governed outputs | PR/commit artifacts | Analysis Artifacts with Run lineage |
| Runtime honesty | Job/run controls | Timeout/cancel + selective budgets |

Still **no Code Agent** in this repo.

---

## 6. Status after M6 freeze

Era 2 M4–M6 are **closed**. See [ERA_1_ERA_2_SUMMARY.md](../era/ERA_1_ERA_2_SUMMARY.md) and [PHASE_M6_RETROSPECTIVE.md](../phase/PHASE_M6_RETROSPECTIVE.md).

**Maturity review (no Era 3 start):** [ERA_3_PLATFORM_MATURITY_REVIEW.md](../era/ERA_3_PLATFORM_MATURITY_REVIEW.md)

**Immediate rule:** discuss any next-phase route separately; **do not** start implementation or reopen Foundation / Era 2 stop-lines in this freeze window.
