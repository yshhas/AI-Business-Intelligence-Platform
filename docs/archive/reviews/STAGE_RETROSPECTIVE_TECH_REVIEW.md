# Stage Retrospective — Tech Review & Next-Knife Decision Basis

**Document type:** Current-version technical review + go/no-go criteria (not an implementation checklist)  
**Status:** Observation window — **no coding authorized**  
**Date:** 2026-07-22  
**Audience:** Product / eng decision gate after E1-AC + E2 freeze  

**Parents:**  
[PLATFORM_CHARTER.md](../../architecture/PLATFORM_CHARTER.md) · [ENHANCEMENT_ROADMAP.md](../roadmap/ENHANCEMENT_ROADMAP.md) ·  
[PHASE_E1_AC_FINAL_STATUS.md](../phase/PHASE_E1_AC_FINAL_STATUS.md) · [PHASE_E2_FINAL_STATUS.md](../phase/PHASE_E2_FINAL_STATUS.md) ·  
[PHASE_NEXT_CANDIDATES.md](../phase/PHASE_NEXT_CANDIDATES.md) · [TECH_INTEGRATION_ASSESSMENT.md](TECH_INTEGRATION_ASSESSMENT.md)

---

## Executive takeaway

本仓已从「ChatBI MVP」演进为可讲述的 **Enterprise Data Agent Platform**：脊柱完整、评测可回归、成本可软约束、权限有 Dataset ACL、SQL 前链路可观测、Analyze 可解释。

当前最大缺口**不再是缺一块 checklist**，而是：

1. **AI 语义准确率**仍依赖真实 NL→SQL 数据与观察，而非再堆平台件；  
2. **下一刀必须证据驱动**（Cost / Repair / Connector），否则回到过早扩张。

**默认决策：Hold — observe only。** 完成本复盘后，用人话证据再选 C1–C4。

---

## 1. Current platform capability panorama

### 1.1 Completed capability chain

```text
Product Shell (Analyze / Tasks / Datasets / ACL)
    → Worker enqueue (capacity · soft token budget)
    → Kernel.run(skill_id)
    → Skill data.bi (fixed LangGraph)
         load_context → link_schema → generate_sql
         → validate (Policy sql.select_gate)
         → execute (Data Plane: file/DuckDB | postgres_ro)
         → summarize / charts / report
    → Trace / Artifacts / steps / platform.*
    → Eval suites (core + quality) in release gate
```

| Layer | What ships today |
|-------|------------------|
| **Kernel** | Skill registry, `run`, Policy hook, Trace materialization — spine stable |
| **Skill** | `data.bi` fixed graph + Schema Linking Lite + heuristic optional (Eval forces off) |
| **Policy** | Deterministic `sql.select_gate` before execute |
| **Data Plane** | `file→DuckDB`, `postgres_ro` (env DSN) |
| **Governance** | Workspace roles + Dataset ACL (`can_read` / `can_run`) + Trace `authorization` |
| **Cost** | Soft workspace UTC-day token budget; enqueue 429 + `budget_rejected` |
| **Eval** | `core` + `quality` golden suites; baselines; heuristic forbidden in Eval |
| **UX** | Analyze explainability: schema / why SQL / policy / resources / artifacts / steps |

### 1.2 Product positioning (current version)

| Is | Is not |
|----|--------|
| **Governed Data Agent Platform** — Skill answers via Policy-gated SQL | ChatBI toy that dumps schema and hopes |
| **Enterprise narrative lite** — permission, budget, Trace, Eval | Full IAM / FinOps / Observability SaaS |
| **One primary Skill (`data.bi`)** proving the spine | Multi-Agent / ReAct free tool loop |
| **Demo + CI-regressible** | Production hyperscale control plane |

**One-liner for stakeholders:**

> Ask a question → Skill links schema → LLM drafts SQL → Policy decides → Plane executes → Trace explains → Eval can regress.

### 1.3 Boundary vs RepoPilot

| Domain | This platform | RepoPilot |
|--------|---------------|-----------|
| Goal | Governed **data** answers (SQL / tables / charts) | **Code** Agent (repo / patch / PR) |
| Loop | Fixed Skill graph + Policy-before-execute | Tool/planner loops over engineering artifacts |
| Retrieval | Schema linking / optional glossary later — **not RAG-over-docs** | Code/doc RAG may belong there |
| Trace | Run Trace for Skill/Policy/Plane | Engineering run / CI / patch audit |
| Forbidden here | Becoming a second RepoPilot (Git, patch, code tools) | Becoming a second Data Agent BI platform |

Cross-ref: [TECH_INTEGRATION_ASSESSMENT.md](TECH_INTEGRATION_ASSESSMENT.md).  
**Rule:** tech that strengthens `Skill → Policy → Plane → Trace` may land here; Code Agent / Git / Patch stays RepoPilot.

---

## 2. Realized gains from completed optimizations

### 2.1 Evaluation Framework (P0-1)

| Before | After |
|--------|-------|
| Gate/path smoke only; NL quality = Demo feel | Golden `core` + CI regression; heuristic forced off |
| Prompt/model changes unfalsifiable | Fail-on-regression vs `baselines/core_latest.json` |

**Gain:** Engineering path honesty + anti-cheat (no silent heuristic in Eval).  
**Limit:** Core still ≠ full semantic NL accuracy; `llm` suite optional; quality suite scores **linking**, not end-to-end LLM accuracy.

### 2.2 Soft Cost Budget (P0-2)

| Before | After |
|--------|-------|
| Tokens in steps; no control | Workspace UTC-day budget; reject before enqueue |
| Surprise spend narrative weak | `failure_class=budget_rejected` + HTTP 429 |

**Gain:** Soft control closes “enterprise can constrain” story without FinOps.  
**Limit:** Budget display / used-vs-cap UX still thin (candidate C2); default budget 0 = off.

### 2.3 Permission / Governance (P1)

| Before | After |
|--------|-------|
| Workspace role ≈ everything | Dataset ACL `can_read` / `can_run`; empty ACL = legacy M5 |
| Authz invisible | Trace `platform.authorization` (audit only) |

**Gain:** Demo “this role can only run this dataset”; ACL ≠ SQL allow (Policy still Gate).  
**Limit:** No column ABAC / tenant IAM / ACL admin UI (intentional ceiling).

### 2.4 E1 Linking + Eval Quality (E1-AC)

| Before | After |
|--------|-------|
| Full schema dump into prompt; opaque | `link_schema` + `link_status` / columns in Trace |
| Silent wide-schema risk | Explicit `fallback_full` / `failed`; quality suite rates |

**Gain:** Pre-generate schema understanding is **observable and regressible**; Eval can track `link_ok_rate` / `link_fallback_rate`.  
**Limit:** Token-overlap linker is lite; Chinese/alias gaps → fallback; **Repair not shipped** — generation/Gate failures still unstructured retry.

### 2.5 E2 Explainability

| Before | After |
|--------|-------|
| Trace JSON / raw node names | Analyze strip: schema · why SQL · policy · resources |
| Authz / link / deny buried | Honest `fallback_full` / deny / first-failure / artifact lineage |

**Gain:** One Run page can answer the five operator questions without a Trace Explorer.  
**Limit:** Understanding lift is **Demo-validated**, not yet measured by UX study; Tasks polish optional; no cost-budget gauge.

---

## 3. Remaining risk ranking

Severity = impact × likelihood given **current** freeze. Not a backlog to clear blindly.

| Rank | Risk theme | Why it still matters | Mitigations already in place | Residual |
|------|------------|----------------------|------------------------------|----------|
| **1** | **AI Quality** | Linker lite + optional LLM; Eval quality ≠ NL accuracy; Repair deferred | Linking Trace, quality suite, heuristic-off Eval, E2 visibility | Highest — observe rates & failure stages |
| **2** | **Cost Control** | Soft budget exists but often off (0); little UI for used/cap; retry/report LLM can still spike when budget unset | Enqueue gate, `llm_total_tokens`, E2 Resources line | Medium — rises if Demo enables budget |
| **3** | **Reliability / Scale** | Sync worker, single-process assumptions, SSE fallback | Capacity / queue limits, cancel/timeout classes, Compose gate | Medium-Low for Demo; High if multi-tenant prod push |
| **4** | **Permission depth** | Dataset ACL enough for narrative; no column/tenant | ACL + authz Trace; Policy allowlist separate | Low–Med — deepen only with real multi-ds sensitivity |
| **5** | **Connector expansion** | Only two planes; third source = copy-paste risk | Policy-first proven on file + postgres_ro | Low until named third source appears |

**Do not reorder by fashion:** Connector is not “next because platforms have connectors.” AI Quality observation outranks Connector until demand is named.

---

## 4. Next-stage decision basis

### 4.1 Observation signals (run these before any authorize)

| Signal | How to read | Owner habit |
|--------|-------------|-------------|
| `link_ok_rate` / `link_fallback_rate` / `link_failed_rate` | Quality suite + baseline over time | `smoke_eval_golden --suite quality` |
| Failure stage mix | First failing `node_name` on live Runs + E2 “First failure” | Analyze Demo notes |
| Budget events | Count of `budget_rejected` / 429 in real use | Tasks filters / logs |
| ACL pain | Requests for column/tenant or “ACL UI” | Stakeholder notes |
| Third source | Named warehouse + who owns credentials | Charter draft |

### 4.2 Go criteria for candidates (all must hold)

#### C1 — Observation toolkit (`eval_diff` lite)

| Go | No-go |
|----|-------|
| Manual JSON compare **blocks** Repair/Cost decisions ≥ 2 cycles | “Nice to have” tooling urge |
| Scope = rates + case pass diff only | Eval SaaS / dashboards / LLM Judge |

#### C2 — Cost display (E3 thin)

| Go | No-go |
|----|-------|
| Budget enabled in Demo/ops **and** ≥ few real `budget_rejected` / confusion “why rejected?” | Budget still 0 everywhere |
| Users cannot explain spend from Task `llm_total_tokens` alone | Building FinOps “because enterprises have billing” |

#### C3 — SQL Repair (E1-B)

| Go (all required) | No-go |
|-------------------|-------|
| Post-link failures dominate (Gate/execute), not linking/`fallback_full` | Failures mostly `no_token_overlap` / empty schema |
| Closed `repair_class` taxonomy fits ≥ majority of sampled fails | Desire for ReAct / free critic agent |
| Eval can score repair without Kernel/Policy rewrite | Softening Gate to “pass more” |

#### C4 — Connector Lite (E4)

| Go | No-go |
|----|-------|
| **Named** third RO source + owner + charter | “We should support MySQL someday” |
| Same Policy-before-execute contract | Connector marketplace / CDC / writes |

### 4.3 Standing Won't Do (this arc)

| Won't Do | Reason |
|----------|--------|
| RAG / Embedding / Vector DB as answer path | Answers from Policy SQL, not doc chunks |
| ReAct / Multi-Agent / free tool loops | Breaks fixed Skill + Policy-before-execute |
| Trace Explorer / Observability platform / LangSmith dual-track | E2 freeze; Analyze is the surface |
| New Trace storage / duplicated execution model | Existing Trace is sole fact source |
| Chat UI / token streaming | Out of product shape |
| Full IAM / tenant / column ABAC (now) | P1 ACL is the ceiling until evidence |
| FinOps / billing / model router | Soft budget + display max |
| Celery / K8s / microservice split | Demo Compose scale intentional |
| Second RepoPilot (Git / patch / code tools) | Domain boundary |
| Checklist-driven expansion without evidence | This document exists to stop that |

---

## 5. Decision record template (use when leaving observation)

Copy when authorizing the next knife:

```text
Date:
Evidence attached:
  - Eval quality summary (link_* rates vs baseline):
  - Failure stage sample (n=__): linking% / generate% / gate% / execute%:
  - Budget/ACL/Connector notes:
Chosen candidate: Hold | C1 | C2 | C3 | C4
Why not the others:
Explicit Won't Do reconfirmed: yes
Next doc: implementation checklist ONLY after this record is approved
```

---

## 6. Version snapshot (freeze day)

| Milestone | Status |
|-----------|--------|
| Era 1–2 Platform Foundation / Enterprise Capability | Frozen |
| P0-1 Eval · P0-2 Soft budget · P1 Dataset ACL | Done / frozen |
| E1-AC Schema Linking + Eval Quality | **Frozen** |
| E2 Analyze Explainability | **Frozen** |
| E1-B Repair · E3 Cost UI · E4 Connector | Not started — evidence-gated |
| Observation window | **Active** |

---

**This retrospective does not authorize coding.**  
Next action: observe → fill §5 record → choose Hold or one of C1–C4 → only then write a thin checklist.
