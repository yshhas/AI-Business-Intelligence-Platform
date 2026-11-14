# Era 3 — Next Value Ranking（after Runtime P0 + Deployment Hygiene）

**Status:** Design only — **no checklist · no coding · no Phase authorized**  
**Date:** 2026-07-22  
**Prerequisite:**  
- E3 Runtime Essentials P0 ✅ frozen — [RETRO](../phase/PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md)  
- E3 Deployment Hygiene ✅ frozen — [RETRO](../phase/PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md)  
**Parents:** [ERA_3_PLATFORM_MATURITY_REVIEW.md](ERA_3_PLATFORM_MATURITY_REVIEW.md) · [ERA_1_ERA_2_SUMMARY.md](ERA_1_ERA_2_SUMMARY.md)

> This document **replaces** the pre-DH ranking recommendation. Historical note: DH was correctly chosen as the first post-P0 slice and is now closed.

---

## 0. Posture after two Era 3 freezes

```text
Era 1–2:  Skill → Policy → Run → Plane → Trace → Permission → Artifact
E3 P0:    Runtime capacity + crash honesty
E3 DH:    Deploy / verify / operate repeatably
```

**Claim now true:** architecture is enterprise-shaped **and** Demo delivery is operable.

**Rule for anything next:** extend **platform identity** (Skill/Policy proof) or close a **proven pain** — do **not** invent more Runtime/ops machinery without evidence.

### Architecture continuity lock (do not overturn)

Kernel · Skill · Policy · Run · Trace · Permission · Artifact · Data Plane  

Any next slice must be **additive** on Product Shell / registry metadata / Worker edges — never a rewrite.

---

## 1. Scoring method

| Criterion | Weight | Question |
|-----------|--------|----------|
| **P** Positioning lift | 30% | Does this strengthen “Enterprise Data Agent Platform” vs BI app? |
| **C** Continuity | 25% | Fits frozen contracts without Kernel/job-platform rewrite? |
| **N** Narrative / Demo / resume value | 25% | Clear one-sentence proof for Demo or CV? |
| **M** Maintainability (inverse cost/risk) | 20% | Thin slice, low drift into overbuild? |

Scores 1–5. Higher = schedule earlier **if** a next slice opens.  
**Drift risk** called out separately; high-drift ideas are demoted even if narrative is tempting.

---

## 2. Candidate assessments

### A. Skill Lifecycle lite

**Thin intent:** `skill_version` on Run/Trace · enable/disable · thin registry metadata. **No** Skill Store / publish portal.

| Criterion | Score | Notes |
|-----------|-------|-------|
| P | **4** | Makes “platform hosts Skills” explicit beyond a single hardcoded path |
| C | **5** | Registry + Run columns / Trace fields; Kernel stays dispatch-only |
| N | **4** | Strong resume line if paired with “version pinned on Run” |
| M | **4** | Small if limited to metadata + Shell gate |
| **Weighted** | **≈ 4.25** | |

| Overbuild if… | Stay thin if… |
|----------------|----------------|
| Plugin marketplace, hot-load, multi-version side-by-side runtime | One version string + config enable map for `data.bi` |

**Verdict:** **Best default next opener** among remaining themes — cheap, continuous, narrative-positive even with one Skill; becomes **mandatory** before a second Skill.

---

### B. Policy Evolution

**Thin intent:** deepen PolicyDecision / Trace explainability (inputs summarized, gate context).  
**Not:** general Policy Framework / ABAC / policy-as-code engine.

| Criterion | Score | Notes |
|-----------|-------|-------|
| P | **3** | Governance story already largely proven by M4 + `sql.select_gate` |
| C | **5** | Additive Trace richness |
| N | **3** | Incremental; harder to Demo as a “new phase” alone |
| M | **3** | Drift into Framework religion is real |
| **Weighted** | **≈ 3.50** | |

| Overbuild if… | Stay thin if… |
|----------------|----------------|
| Policy engine, composition DSL, second product surface | Extra fields on existing `PolicyDecision` / Trace panel |

**Verdict:** **Opportunistic companion**, not a phase driver. Prefer bundling a small Trace enrichment into another slice rather than a dedicated Policy phase.

---

### C. Runtime deferred — workspace concurrency / `replay_of`

| Item | Worth now? | Why |
|------|------------|-----|
| **Workspace concurrency** | **Low–Medium** | Global in-flight + queue depth already tell the capacity story; per-workspace fairness matters only with multi-tenant contention evidence |
| **`replay_of`** | **Low–Medium** | Honest “new Run” already exists; lineage link is UX sugar, not platform identity |

| Criterion | Score | Notes |
|-----------|-------|-------|
| P | **2** | Ops polish; weak positioning vs Skill/Policy |
| C | **5** | Same Worker / task_service seams as P0 |
| N | **2** | Hard to make Demo-heroic after P0+DH |
| M | **4** | Technically easy — risk is **opportunity cost** (Runtime complexity creep) |
| **Weighted** | **≈ 3.05** | |

**Verdict:** **Defer**. Reopen only with concrete multi-workspace starvation or operator “replay lineage” demand. Doing now is **mild overbuild relative to Era 3 goals**.

---

### D. Second Skill (platform expansion proof)

**Valid only if** it proves Kernel extensibility — not a second BI feature pack.

| Criterion | Score | Notes |
|-----------|-------|-------|
| P | **5** | Strongest “this is a Platform” proof |
| C | **4** | High if Skill uses Kernel/Tool/Policy/Trace/Artifact contracts |
| N | **5** | Excellent Demo/resume if charter is crisp |
| M | **2** | Highest delivery + drift risk (scope explosion) |
| **Weighted** | **≈ 4.15** | |

**Necessity:** **Not required to close Era 3 credibility** after P0+DH. **Strategic optional** — do not invent a Skill “for quantity.”

| Good second Skill | Bad second Skill |
|-------------------|------------------|
| Different Tool/Policy needs, same Run/Trace/Artifact | More charts / prettier report |
| Thin domain (e.g. schema explain, SQL lint-only) | Full second product |
| Uses enable + skill_version | Bypasses Kernel |

**Gate order:** Skill Lifecycle lite → written second-Skill charter → implement Skill.  
**Without charter:** do **not** start.

---

### E. Other Enterprise readiness crumbs

| Idea | Score sense | Verdict |
|------|-------------|---------|
| GitHub Actions wrapping `smoke_release_gate` | High continuity, low drama | **Optional hygiene** — not a “phase”; do when CI pain appears |
| API/Worker Dockerfile | Medium | **Defer** until target host requires it |
| Worker HTTP health | Low after DH decision | **Stay out** this era |
| Retention / Artifact expiry | Low | **Out** (M6 freeze) |
| Thin Skill enable in Shell UI | Follows A | Part of Skill Lifecycle lite if opened |

---

## 3. Ranking (post-DH)

| Rank | Theme | ≈ Score | Recommendation |
|------|-------|---------|----------------|
| **1** | **Skill Lifecycle lite** | **≈ 4.25** | **Recommended next Era 3 slice** (checklist only after confirm) |
| **2** | **Second Skill** | **≈ 4.15** | Trigger-gated; **after** lifecycle lite + charter |
| **3** | Policy Trace deepening | **≈ 3.50** | Companion / opportunistic — not solo phase |
| **4** | Runtime deferred (workspace / replay_of) | **≈ 3.05** | Evidence-gated only |
| **5** | CI Actions / Dockerfile | — | Ops crumbs, not ranking winners |

```text
E3 P0 Runtime Essentials     ✅ frozen
E3 Deployment Hygiene        ✅ frozen
        │
        ▼
Recommended next: Skill Lifecycle lite
        │
        ├─ then (optional): Second Skill charter → thin Skill
        ├─ opportunistic: Policy Trace fields
        └─ later / evidence: workspace cap, replay_of, Actions, Dockerfile
```

---

## 4. Recommended next knife

### **Skill Lifecycle lite**

**Why first now**

1. **Positioning:** closes the gap between “one Skill demo” and “platform that manages Skills.”  
2. **Continuity:** zero Kernel rewrite; Run/Trace already carry `skill_id`.  
3. **Narrative:** clear Demo — Run shows `skill_id` + `skill_version`; disable blocks enqueue.  
4. **Cost:** small metadata + Shell gate; unlocks second Skill safely later.  
5. **Avoids:** more Runtime after P0 (diminishing returns) and premature second Skill.

**Suggested thin scope (design hint only — not a checklist)**

- Persist `skill_version` on Run / Trace  
- Config/registry enable flag for `data.bi`  
- Enqueue deny when disabled  
- **Out:** store, marketplace, multi-version runtime, UI Skill catalog product  

---

## 5. Can permanently skip (or near-permanently)

| Direction | Why |
|-----------|-----|
| Auto-retry / checkpoint resume | Breaks Trace/Artifact honesty |
| Celery / Kafka / Streams rewrite | P0+Redis List thesis already proven |
| Priority scheduler / FinOps / hard-kill | Job-platform / FinOps product |
| Policy Framework / ABAC engine | One gate family; ceremony without need |
| Skill marketplace / plugin hot-load | Security + product surface ≠ this thesis |
| Worker HTTP health (after DH) | Explicitly rejected; docs sufficient |
| IAM / SSO / Invite suite | M5 thin RBAC is the ceiling |
| Connector Framework / Catalog / ETL | M3 freeze |
| Report Center / CMS / PDF / Artifact gallery | M6 freeze |
| Multi-Agent mesh / Code Agent | Charter / RepoPilot boundary |

---

## 6. Overbuild warnings (doing now would be wrong)

| If you start… | You are overbuilding because… |
|---------------|-------------------------------|
| More Runtime (caps/replay) without incidents | Capacity story already closed in P0 |
| Second Skill without charter + lifecycle | Looks like feature dump, not platform proof |
| Policy Framework | Trace already carries deny; engine has no second policy kind |
| APM / Dockerfile / Actions as a “phase” | DH already delivered operable Demo; these are optional crumbs |
| Anything that rewrites Kernel or Run model | Breaks Era 1–2 continuity lock |

---

## 7. Decision gate (human)

| Option | Meaning |
|--------|---------|
| **Stay frozen** | Resume / Demo with P0+DH; no new slice |
| **Confirm Skill Lifecycle lite** | Next: write checklist (design only), then authorize coding |
| **Charter second Skill first** | Only if external narrative demands Kernel proof now — still do lifecycle before/with it |
| **Reject** opening Runtime deferred / Policy Framework / APM as next phase | Aligns with this ranking |

**This ranking does not authorize coding and does not create a checklist.**

---

## 8. Related

- [PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md](../phase/PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md)  
- [PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md](../phase/PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md)  
- [ERA_3_PLATFORM_MATURITY_REVIEW.md](ERA_3_PLATFORM_MATURITY_REVIEW.md)  
- [ERA_1_ERA_2_SUMMARY.md](ERA_1_ERA_2_SUMMARY.md)  
