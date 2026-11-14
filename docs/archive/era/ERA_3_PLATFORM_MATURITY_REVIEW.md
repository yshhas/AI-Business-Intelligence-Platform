# Era 3 — Platform Maturity Review

**Document type:** Architecture / product maturity assessment  
**Status:** Review only — **no coding · no new Phase · Era 3 not started**  
**Date:** 2026-07-22  
**Prerequisite:** Era 1 (M0–M3) + Era 2 (M4–M6) **frozen**  
**Parents:** [ERA_1_ERA_2_SUMMARY.md](ERA_1_ERA_2_SUMMARY.md) · [PLATFORM_CHARTER.md](../../architecture/PLATFORM_CHARTER.md) · [ENTERPRISE_CAPABILITY_ROADMAP.md](../roadmap/ENTERPRISE_CAPABILITY_ROADMAP.md)

---

## 0. Purpose

Era 1 / Era 2 closed the **core migration**:

```text
ChatBI Application
        ↓
Enterprise Data Agent Platform
```

| Era | Proven chain |
|-----|----------------|
| **1** | Skill → Policy → Run → Data Plane |
| **2** | Run → Trace → Permission → Artifact |

This review asks: **what still separates “Demoable enterprise narrative” from “credible Enterprise Agent Platform operations”?**  
It ranks gaps by **value · risk · continuity with the frozen architecture** — without proposing large rewrites or starting Era 3.

**Outcomes of this doc**

1. Honest maturity snapshot  
2. Ranked candidate themes (if Era 3 ever opens)  
3. Explicit **never-do** list (protect positioning)  
4. A decision gate: start Era 3 / stay frozen / only ops hygiene  

---

## 1. Maturity snapshot (after M6)

### 1.1 What is already “platform”

| Capability | Maturity | Evidence |
|------------|----------|----------|
| Kernel dispatch (Skill/Tool/Policy/Artifact) | **Solid (Demo)** | In-memory registry; Facade → `kernel.run` |
| First Skill `data.bi` | **Solid (Demo)** | LangGraph adapter; golden Analyze path |
| Policy-before-select | **Solid (Demo)** | `sql.select_gate` + Tool wrap; plane-agnostic |
| Run lifecycle | **Solid (Demo)** | timeout / cancel / `failure_class`; Worker-owned |
| Multi data plane | **Thin but proven** | `file` \| `postgres_ro` behind same Tool/Policy |
| Execution Trace | **Solid (Demo)** | `platform.execution`; query filters; Trace UI |
| Resource permission | **Thin but proven** | Workspace + role matrix; no Kernel RBAC |
| Artifact entity | **Thin but proven** | `run_artifacts` metadata + content_ref + lineage |

### 1.2 What is still “Demo / single-operator”

| Gap class | Today | Enterprise bar |
|-----------|-------|----------------|
| Worker topology | Single consumer Redis List loop | Predictable concurrency & backpressure |
| Failure recovery | No auto-retry; manual re-run | Explicit policy for transient vs poison |
| Skill ops | One hardcoded Skill; no version pin | Pin / enable without redeploy theater |
| Policy surface | One SQL gate family | Composition without framework religion |
| Deploy/obs | Compose + logs + smokes | Reproducible env + Run-correlated signals |
| Expansion proof | One Skill only | Second Skill *proves Kernel*, not feature dump |

### 1.3 Positioning verdict

| Claim | Status |
|-------|--------|
| “Not a BI app — a governed Data Agent Platform” | **Achieved** for narrative / Demo |
| “Enterprise-ready operations platform” | **Not yet** — gaps are ops & lifecycle thinness, not missing Report Center |
| “Needs Celery / IAM / CMS to be enterprise” | **False** — those are overbuilds relative to this architecture |

---

## 2. Evaluation method

Weights (same spirit as Era 2 ranking):

| Criterion | Weight | Question |
|-----------|--------|----------|
| **V** Enterprise / ops value | 35% | Does this close a real credibility gap vs Demo? |
| **C** Continuity | 30% | Extends Worker / Shell / Trace / registry without Kernel rewrite? |
| **R** Risk of product drift | 20% | Inverse score: high risk of CMS/IAM/framework → low priority |
| **E** Controllability | 15% | Thin slice possible in one phase? |

Scores 1–5. Higher = schedule earlier **if** Era 3 opens.  
**Risk column** in tables below is raw drift risk (5 = dangerous); ranking uses **(6 − risk)** for R.

---

## 3. Focus area assessments

### 3.1 Runtime Production Readiness

**As-is:** Cooperative timeout/cancel; Redis List dequeue; single-process worker; no auto-retry; terminal states honest.

| Topic | Need? | Continuity | Drift risk | Note |
|-------|-------|------------|------------|------|
| Concurrency model | Medium–High | High — Worker-only | Medium | Per-workspace / global max in-flight Runs; still one queue OK |
| Resource budgets | Medium | High — Shell/Worker | Medium | Timeout already exists; add cheap caps (rows/time already partial) — avoid token-billing product |
| Queue reliability | Medium | High — Redis List | Medium | Visibility timeout / reclaim orphaned `running`; poison handling |
| Retry / replay | **Low–Medium** | High if **manual** | **High** if auto | Prefer **explicit replay** (new Run) over silent retry; auto-retry fights Trace honesty |

**Thin candidates (if Era 3):**

1. Worker concurrency limit + claim heartbeat / stale `running` reclaim  
2. Documented failure taxonomy → “safe to replay?” flag (not engine)  
3. Optional max queue depth / reject enqueue with clear `failure_class`  

**Not candidates:** Celery/Kafka rewrite, distributed saga, guaranteed LLM/DB kill, exactly-once.

**Verdict:** Highest **continuity** path to “production-ish.” Does not change Kernel story. Rank **#1 theme** for Era 3 *if* started for ops credibility.

---

### 3.2 Skill Lifecycle

**As-is:** In-memory `register_skill`; single `data.bi`; Run may carry `skill_id` string; no version / enable flag.

| Topic | Need? | Continuity | Drift risk | Note |
|-------|-------|------------|------------|------|
| Version pin on Run | Medium (rises with 2nd Skill) | High — metadata on Run/Trace | Low | `skill_id` + `skill_version` label only |
| Skill metadata | Low–Medium | High | Low | id, title, owner domain, status |
| Publish / enable / disable | Medium when multi-skill | Medium — Shell gate | Medium | Disable → enqueue deny; Kernel still dumb |
| Full Skill store | **No** | Low | **Very high** | Marketplace / plugins |

**Thin candidates:**

1. `skill_version` string recorded on Run + Trace (even if always `1`)  
2. Shell-level enable map for registered skills (config, not DB marketplace)  

**Trigger:** A **second Skill decision** — until then, version pin is cheap insurance; full lifecycle is premature.

**Verdict:** Rank **#2–3** as *thin metadata*. Do **not** open Skill Ops product with one Skill.

---

### 3.3 Policy Evolution

**As-is:** `sql.select_gate` as the real policy; `PolicyDecision` already in Trace; Tool wrap is Policy-first.

| Topic | Need? | Continuity | Drift risk | Note |
|-------|-------|------------|------------|------|
| Keep SQL gate as primary | Yes | — | — | Already enterprise-shaped for Data Agent |
| “General Policy Framework” | **Low now** | Medium | **High** | Framework religion without second policy family |
| Policy composition | Low–Medium | Medium | High | AND of allowlists is enough until a 2nd policy type exists |
| Policy evaluation in Trace | **Mostly done** | High | Low | Enrich reasons / call_id already; deepen only if gaps found |
| ABAC / policy-as-code engine | **No** | Low | **Very high** | IAM-adjacent |

**Thin candidates:**

1. Stronger **evaluation narrative** in Trace (inputs summarized, not only ok/reason)  
2. Second **policy id** only when a second *gate kind* appears (e.g. row budget) — still functions, not a framework  

**Verdict:** Prefer **deepening Trace of existing Policy** over inventing a Policy Framework. Rank **#4** unless a concrete second gate is required by Runtime budgets.

---

### 3.4 Enterprise Deployment

**As-is:** Docker Compose, env-based config, Python smokes, app logs; Trace/API for Run-centric truth.

| Topic | Need? | Continuity | Drift risk | Note |
|-------|-------|------------|------------|------|
| Config management | Medium | High — env / settings | Medium | Documented config matrix; secrets hygiene; no Consul product |
| Observability | Medium | High — extend logs + Trace ids | Medium | Correlate `task_id` / `run_id` in worker logs; health endpoints |
| Deployment reproducibility | Medium | High — Compose pin | Low | Image tags, migration gate, smoke-in-CI |
| Full APM / SIEM | **No** | Low | **High** | Conflicts with M4 freeze intent |

**Thin candidates:**

1. “Operator pack”: config checklist + health + smoke suite as release gate  
2. Structured log fields aligned with Trace (`run_id`, `skill_id`, `failure_class`)  

**Verdict:** High **practical** value, low story drama — often done as **hygiene alongside** Runtime readiness, not a separate product Phase. Rank **#2 companion**.

---

### 3.5 Agent Capability Expansion (second Skill)

**As-is:** Kernel registry can hold many skills; product path assumes `data.bi`.

| Topic | Need? | Continuity | Drift risk | Note |
|-------|-------|------------|------------|------|
| Second Skill to prove Kernel | **Strategic, not urgent** | High if Skill is thin | **High** if BI feature pack | Must prove *platform extension*, not ChatBI v2 |
| Multi-Agent orchestration | **No** | Low | **Very high** | Charter anti-goal for this era |
| Code / Engineering Skill | **No (this repo)** | — | — | RepoPilot boundary |

**What a valid second Skill looks like**

| Good proof | Bad proof |
|------------|-----------|
| Different Tool/Policy needs, same Kernel/Run/Trace/Artifact | More chart types / nicer report |
| Reuses Trace + Permission + Artifact contracts | Private pipeline that bypasses Kernel |
| Thin domain (e.g. schema-explain, SQL-lint-only, metrics snapshot) | “Full second BI product” |
| Shows enable/disable + skill_id on Run | Plugin marketplace |

**Verdict:** Second Skill is an **Era 3 optional proof**, not the default opener. Schedule **after** Runtime/Skill-metadata thinness, or as a **deliberate platform demo** with a one-page charter. Rank **#5** unless positioning review demands Kernel proof sooner.

---

## 4. Ranked themes (if Era 3 opens)

| Rank | Theme | Weighted sense | Continuity | Primary risk |
|------|-------|----------------|------------|--------------|
| **1** | **Runtime Production Readiness** (concurrency, reclaim, enqueue limits; **no** auto-retry engine) | Highest ops value | Worker / queue only | Becoming a job platform |
| **2** | **Enterprise Deployment hygiene** (config matrix, health, smoke-as-gate, structured logs) | High practical | Compose / Shell | APM/SIEM productization |
| **3** | **Skill Lifecycle lite** (version pin + enable flag; no store) | Medium; unlocks #5 | Registry + Run metadata | Skill marketplace |
| **4** | **Policy deepening** (Trace richness; optional second *gate function*) | Medium–Low | Existing PolicyDecision | “Policy Framework” rewrite |
| **5** | **Second Skill (platform proof)** | Strategic optional | Kernel registry | Multi-Agent / BI expansion |

### Suggested Era 3 shape (design only — not approved)

```text
IF Era 3 starts:
  Prefer:  Runtime readiness (+ deploy hygiene companion)
  Then:    Skill version/enable metadata
  Later:   Second Skill charter → thin Skill
  Avoid:   Policy Framework / Celery / IAM / CMS as openers
```

Retry/replay stance:

| Mode | Recommendation |
|------|----------------|
| Silent auto-retry | **Do not** — muddies Trace & Artifact lineage |
| Operator “Replay as new Run” | **OK** — new `run_id`, links optional `replay_of` |
| Mid-run checkpoint resume | **Out** — saga territory |

---

## 5. Forever (or near-forever) out

These remain **anti-goals** relative to this platform’s identity — not “later backlog filler”:

| Never (as platform core) | Why |
|--------------------------|-----|
| **Report Center / Artifact CMS** | Turns Agent Platform into BI document product |
| **PDF / Export farm** | Same drift; content_ref already enough |
| **IAM / SSO / Invite org suite** | Product Shell thin RBAC is the ceiling until a hard multi-tenant trigger |
| **Connector Framework / Catalog / ETL** | M3 proved planes; framework is a different company |
| **Artifact Marketplace / global gallery** | Breaks Run-scoped governance story |
| **Multi-Agent orchestration mesh** | Complexity without Data Agent thesis |
| **Code Agent in this repo** | RepoPilot boundary |
| **Celery/Kafka “real job platform” rewrite** | Disproportionate to Demo→ops gap |
| **Standalone Audit/SIEM microservice** | M4 Trace is the chosen model |
| **Policy-as-code / ABAC engine** | Without many policy kinds, pure ceremony |
| **Skill plugin marketplace / hot-load store** | Security + ops theater |

**Rule:** If a proposal requires one of the above to “feel enterprise,” the proposal is wrong for *this* architecture.

---

## 6. Distance to “true” Enterprise Agent Platform

| Dimension | Distance | Closer via |
|-----------|----------|------------|
| Governed execution story | **Near** | Already M1–M6 |
| Operator production confidence | **Medium gap** | Runtime readiness + deploy hygiene |
| Multi-skill platform proof | **Latent gap** | Thin second Skill + version pin |
| Policy generality | **Mostly sufficient** | Deepen Trace; don’t frameworkize |
| Enterprise org packaging | **Out of scope** | IAM/SSO — explicitly not the thesis |

**One-line maturity:**

> The platform is **architecturally enterprise-shaped** and **operationally Demo-grade**. Era 3 should close *ops honesty*, not invent new product surfaces.

---

## 7. Decision gate — start Era 3?

| Option | When |
|--------|------|
| **Stay frozen** | Resume / hiring / Demo polish only; no new credibility pressure |
| **Open Era 3 (narrow)** | Need production-ish Worker behavior or CI/deploy reproducibility for real users |
| **Open Era 3 (platform proof)** | External narrative demands “more than one Skill” — with a written second-Skill charter first |
| **Do not open Era 3 for…** | Charts, PDF, IAM, connectors, Multi-Agent, Report Center |

**This review does not start Era 3.**  
Next human decision: pick an option above; only then write a checklist.

**Follow-up:**  
- E3 P0 frozen: [PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md](../phase/PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md)  
- E3 DH frozen: [PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md](../phase/PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md)  
- Pre-DH ranking (refresh before next coding): [ERA_3_NEXT_VALUE_RANKING.md](ERA_3_NEXT_VALUE_RANKING.md)

---

## 8. Related

- [ERA_1_ERA_2_SUMMARY.md](ERA_1_ERA_2_SUMMARY.md)  
- [PHASE_M6_RETROSPECTIVE.md](../phase/PHASE_M6_RETROSPECTIVE.md)  
- [ENTERPRISE_CAPABILITY_ROADMAP.md](../roadmap/ENTERPRISE_CAPABILITY_ROADMAP.md)  
- [ENTERPRISE_M4_M6_RANKING.md](../roadmap/ENTERPRISE_M4_M6_RANKING.md) (historical scoring method)
