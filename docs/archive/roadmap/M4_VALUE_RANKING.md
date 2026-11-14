# M4 Value Ranking — post-M3

**Context:** M1 + M2 + M3 are frozen. Story review: [PLATFORM_STORY_REVIEW.md](../reviews/PLATFORM_STORY_REVIEW.md).  
**Question:** If (and only if) a next phase opens, which theme strengthens the platform *without* reopening connector/ETL scope?

Candidates (user-requested):

1. **Audit thin enhancement**  
2. **RBAC companion** (not IAM phase)  
3. **Artifact / Report capability**  
4. **Continue frozen** (docs/Demo only)

---

## Scoring criteria (same weights as M2/M3)

| Criterion | Weight |
|-----------|--------|
| A. Platform positioning lift | 35% |
| B. Complementarity vs RepoPilot | 25% |
| C. Demo / resume narrative | 25% |
| D. Controllability | 15% |

Scores 1–5.

---

## 1. Audit thin enhancement

**Story:** Query/export governed traces — Tool / Policy / Run / data_plane — without an audit microservice.

| Criterion | Score | Notes |
|-----------|-------|-------|
| A Positioning | **4** | Deepens “governed agent”; pairs with M2/M3 honesty |
| B vs RepoPilot | **5** | Strongest *symmetry* with Engineering Agent audit/safety narrative |
| C Demo | **3** | Interview deep-dive strong; less visual than charts/planes |
| D Controllability | **4** | Extend steps + `platform.*`; easy to overbuild if unchecked |
| **Weighted** | **≈ 3.95** | |

**M4 shape if chosen:**  
Filter/list/export by `failure_class`, `skill_id`, `source_type`; optional `policy_denied` / `connector_error` views. **No** new audit DB product.

---

## 2. RBAC companion

**Story:** Tighten who binds RO sources / who runs against which dataset.

| Criterion | Score | Notes |
|-----------|-------|-------|
| A Positioning | **2** | Enterprise hygiene; weak Kernel/Data-Agent story |
| B vs RepoPilot | **2** | Generic SaaS; low distinctiveness |
| C Demo | **2** | Denial screens; hard to show platform depth |
| D Controllability | **4** | Small checks on existing roles (owner/analyst already used) |
| **Weighted** | **≈ 2.30** | |

**Better as:** fold into whatever M4 opens (if any), not a phase theme. Invite/IAM still forbidden.

---

## 3. Artifact / Report capability

**Story:** Richer report/chart artifacts on the same Skill.

| Criterion | Score | Notes |
|-----------|-------|-------|
| A Positioning | **2** | Reads as BI product polish, not platform evolution |
| B vs RepoPilot | **2** | Little complementarity signal |
| C Demo | **4** | Visually strong; easy to show |
| D Controllability | **3** | Scope creep (PDF, pie, templates) historically high |
| **Weighted** | **≈ 2.65** | |

**Risk:** Re-centers narrative on ChatBI features and away from Agent Platform.

---

## 4. Continue frozen

**Story:** Polish Demo/docs against the M1–M3 script; no new phase.

| Criterion | Score | Notes |
|-----------|-------|-------|
| A Positioning | **3** | Protects completed arc; no new claim |
| B vs RepoPilot | **3** | Positioning already clear post-M3 |
| C Demo | **5** | Best use of time if narrative delivery is the bottleneck |
| D Controllability | **5** | Zero blast radius on frozen contracts |
| **Weighted** | **≈ 3.80** | |

---

## Ranking

| Rank | Theme | ≈ Score | Role |
|------|-------|---------|------|
| **1** | **Audit thin enhancement** | **3.95** | Best *capability* M4 if a phase is required |
| **2** | **Continue frozen** | **3.80** | **Recommended default now** |
| 3 | Artifact / Report | 2.65 | Product polish only — avoid as platform phase |
| 4 | RBAC companion | 2.30 | Companion checks only |

---

## Recommendation

### Preferred next action: **Stay frozen**

M1–M3 already complete the core Demo arc (Skill → Policy → Run → Data Plane). Spend cycles on:

- Demo script rehearsal  
- Charter / Contracts / README consistency  
- Optional: record a short walkthrough

### If M4 must open a capability theme: **Audit thin slice**

Choose when the audience cares more about **governance symmetry with RepoPilot** than about new visuals.

### Explicitly not M4 themes

- Connector Framework / more sources / Catalog / ETL  
- Second Skill / Multi-Agent  
- Full IAM / invite RBAC product  
- Large Artifact redesign as “platform work”

---

## Decision (historical — post-M3, then superseded)

Originally confirmed **stay frozen**.  

**Superseded 2026-07-22:** M1–M3 = **Platform Foundation complete**, not project end.  
Era 2 roadmap + new ranking:

- [ENTERPRISE_CAPABILITY_ROADMAP.md](ENTERPRISE_CAPABILITY_ROADMAP.md)  
- [ENTERPRISE_M4_M6_RANKING.md](ENTERPRISE_M4_M6_RANKING.md) → **M4 = Traceable Execution**
