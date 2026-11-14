# Era 2 — M4 / M5 / M6 Priority Ranking

**Context:** Era 1 Platform Foundation (M0–M3) complete.  
**Parent:** [ENTERPRISE_CAPABILITY_ROADMAP.md](ENTERPRISE_CAPABILITY_ROADMAP.md)  
**Supersedes:** “stay frozen forever” as default in [M4_VALUE_RANKING.md](M4_VALUE_RANKING.md) (kept as historical post-M3 note)

**Scoring weights**

| Criterion | Weight |
|-----------|--------|
| A. Enterprise necessity (gap vs “real platform”) | 30% |
| B. Platform positioning lift | 25% |
| C. Builds on M1–M3 assets / boundary safety | 20% |
| D. Complementarity vs RepoPilot | 15% |
| E. Controllability (thin slice feasible) | 10% |

Scores 1–5. Higher = schedule earlier.

---

## Candidates

1. Audit / Observability → **Traceable Execution Model**  
2. Resource-level Permission / RBAC (thin)  
3. Artifact lifecycle (lite)  
4. Skill lifecycle  
5. Runtime advanced governance  

---

## 1. Audit / Observability — Traceable Execution Model

**Not:** a Demo “trace panel” vanity feature.  
**Is:** first-class, queryable model of *what the Agent did* under Policy / Run / Plane.

| Criterion | Score | Notes |
|-----------|-------|-------|
| A Enterprise necessity | **5** | Without queryable traces, “governed” is only runtime folklore |
| B Positioning | **5** | Upgrades Foundation → Enterprise Agent credibility |
| C Asset fit | **5** | Extends steps + `platform.*` + `failure_class`; Kernel untouched |
| D vs RepoPilot | **5** | Symmetric governance vocabulary, data domain |
| E Controllability | **4** | Thin API/export/index; risk = overbuilding audit product |
| **Weighted** | **≈ 4.90** | |

**M4 thin slice (intent):**

- Run-centric execution record: skill, tools, policy decisions, plane, terminals, `failure_class`  
- Filter/query: workspace, status, `failure_class`, `source_type`, time range  
- Export (JSON) for Demo/compliance walkthrough  
- **No** new microservice; **no** parallel event bus  

**Out:** SIEM, WORM, anomaly ML, rewriting Kernel to emit spans.

---

## 2. Resource-level Permission / RBAC (thin)

| Criterion | Score | Notes |
|-----------|-------|-------|
| A Enterprise necessity | **5** | Multi-plane + audit implies “who may bind/run/view” |
| B Positioning | **3** | Enterprise hygiene; weaker Kernel story alone |
| C Asset fit | **4** | Extends roles already on members; keep out of Kernel |
| D vs RepoPilot | **3** | Shared “authz” idea; less distinctive than traces |
| E Controllability | **4** | Dataset/Run/plane ACL matrix lite; invite/IAM forbidden |
| **Weighted** | **≈ 3.95** | |

**M5 thin slice (intent):**

- Explicit permissions: bind `postgres_ro`, run Analyze, view Run/traces, cancel  
- Resource scope: Workspace + Dataset (+ optional Run creator rules)  
- Deny paths visible in Audit (M4)  

**Out:** Org IAM, invite UI, SSO product, ABAC language.

---

## 3. Artifact lifecycle (lite)

| Criterion | Score | Notes |
|-----------|-------|-------|
| A Enterprise necessity | **4** | Governed *outputs* matter after traces exist |
| B Positioning | **3** | Platform if framed as lineage; BI if framed as prettier reports |
| C Asset fit | **4** | Artifact contract already in Kernel types |
| D vs RepoPilot | **3** | Analogous to governed change artifacts |
| E Controllability | **3** | Easy drift into export/CMS scope |
| **Weighted** | **≈ 3.50** | |

**M6 thin slice (intent):**

- Stable artifact ids tied to `run_id`  
- Retention / list-by-run API  
- Optional “primary report” pointer  

**Out:** PDF product, collaborative docs, chart type explosion.

---

## 4. Runtime advanced governance

| Criterion | Score | Notes |
|-----------|-------|-------|
| A Enterprise necessity | **3** | Budgets/concurrency real; M2 already covers core honesty |
| B Positioning | **3** | Ops depth; less “Enterprise Agent” than Audit/ACL |
| C Asset fit | **4** | Worker-side only; Kernel stays sync executor |
| D vs RepoPilot | **3** | Shared run-control theme |
| E Controllability | **2** | High temptation toward job-platform rewrite |
| **Weighted** | **≈ 3.10** | |

**Selective later (companion / M6b):**

- Per-workspace concurrency cap  
- Optional token/time budget soft-fail → `failure_class`  

**Out:** Celery, lease fencing clusters, guaranteed mid-query kill.

---

## 5. Skill lifecycle

| Criterion | Score | Notes |
|-----------|-------|-------|
| A Enterprise necessity | **2** | One Skill (`data.bi`); ops theater without second Skill |
| B Positioning | **2** | Looks mature; little Demo proof with N=1 |
| C Asset fit | **3** | Registry exists but in-memory / process-local |
| D vs RepoPilot | **2** | Weak complementarity signal alone |
| E Controllability | **3** | Version string cheap; full lifecycle not |
| **Weighted** | **≈ 2.25** | |

**Defer** until a second Skill is explicitly approved.  
**Optional crumb in M4:** persist `skill_id` + optional `skill_version` on Run trace (already mostly true).

---

## Ranking → schedule

| Rank | Theme | ≈ Score | Phase |
|------|-------|---------|-------|
| **1** | **Audit / Observability (Traceable Execution)** | **4.90** | **M4** |
| **2** | **Resource-level Permission (thin)** | **3.95** | **M5** |
| **3** | **Artifact lifecycle (lite)** | **3.50** | **M6** |
| 4 | Runtime advanced (selective) | 3.10 | **M6 companion / M6b** |
| 5 | Skill lifecycle | 2.25 | **Trigger-gated (post–second Skill)** |

```text
M4  Traceable Execution Model
M5  Resource Authorization (thin)
M6  Artifact Lifecycle lite
    └─ optional: Runtime budget/concurrency companion
Later  Skill lifecycle (only with second Skill decision)
```

---

## Why this order

1. **Audit first** — makes Foundation *evidence-based*; unblocks permission Demo (“denied + why”) and artifact lineage (“output of Run X”).  
2. **Permission second** — enterprise data plane without authz is incomplete; without traces, authz Demo is weak.  
3. **Artifacts third** — govern outputs once execution is queryable.  
4. **Runtime advanced** — optimize control plane after you can observe it.  
5. **Skill lifecycle** — avoid platform cosplay with a single Skill.

---

## Boundary reminder for all Ms

- Do **not** move Run lifecycle into Kernel  
- Do **not** put ACL engines inside Kernel  
- Do **not** bypass Policy for “observability injectors” that execute SQL  
- Do **not** open Connector Framework under Observability costume  

---

## Decision request

1. **Confirm Era 2 roadmap** + schedule **M4 = Traceable Execution (Audit/Observability)**  
2. Confirm **M5 = thin Resource Permission**, **M6 = Artifact lifecycle lite**  
3. Confirm Skill lifecycle + Connector Framework remain **out** until explicit reopen  

After confirmation → **Phase M4 Checklist (design only)** before any coding.

**Update:** Sequence confirmed; checklist published: [PHASE_M4_CHECKLIST.md](../phase/PHASE_M4_CHECKLIST.md).
