# Platform Story Review — post-M3

**Status:** Review complete (2026-07-22)  
**Context:** M1 / M2 / M3 formally frozen. No M4 coding until ranking decision.

---

## 1. Does the Platform Charter need an update?

**Verdict: Yes — additive docs only (done alongside this review).**

| Charter theme | Pre-M3 | Post-M3 needed? |
|---------------|--------|-----------------|
| Runtime / Kernel | Present | Keep; clarify Kernel ≠ lifecycle ≠ data plane |
| Policy | Present (`sql.select_gate`) | Keep; state Policy is **plane-agnostic** |
| Run Governance | Present (M2 limitations) | Keep; extend limitations to Postgres RO queries |
| Data Plane | Missing / deferred as “no connectors” | **Add** — file + postgres_ro as governed planes, not Connector Framework |

Non-goals that must flip from “deferred forever” wording to “M3 proved thin RO; framework still out”:

- External warehouse connectors → **thin postgres_ro in; framework still out**

See updated [PLATFORM_CHARTER.md](../../architecture/PLATFORM_CHARTER.md).

---

## 2. Is the Demo story complete across three phases?

**Verdict: Yes — core Enterprise Data Agent Platform arc is Demo-ready.**

```text
Skill execution          (M1)
        ↓
Policy governed          (M1, verified on both planes in M3)
        ↓
Run lifecycle managed    (M2)
        ↓
Multiple data planes     (M3)
```

### Suggested Demo script (one sitting)

| Beat | Show |
|------|------|
| 1 Platform | `kernel.run` + `skill_id=data.bi` in result |
| 2 Policy | Illegal / non-allowlist SQL → `policy_denied` (file or postgres_ro) |
| 3 Run | Cancel or short timeout → terminal + `failure_class` |
| 4 Data plane A | Upload file → Analyze → charts/report |
| 5 Data plane B | Bind postgres_ro → Analyze → `platform.data_plane.source_type=postgres_ro` |
| 6 Contrast | Same Skill / Policy / Worker; different executor |

### Story completeness scorecard

| Question | Answer |
|----------|--------|
| Can we claim “Platform + Skill” without BI-app confusion? | **Yes** (M1) |
| Can we claim “governed Agent Run”? | **Yes** (M2) |
| Can we claim “enterprise data,” not only file upload? | **Yes** (M3) |
| Do we need a fourth beat for a resume/Demo? | **Optional** — Audit symmetry or stay frozen |

**Gap that is OK to leave:** no Catalog, no multi-source UX, no second Skill — those would start a *different* product story.

---

## 3. Positioning vs RepoPilot (story check)

| Shared vocabulary | RepoPilot instantiation | This platform instantiation |
|-------------------|-------------------------|-----------------------------|
| Tools | Engineering tools | `sql.*` / chart / report |
| Policy / Gate | Change-safety style gates | `sql.select_gate` + RO executor |
| Run honesty | Engineering run governance | timeout / cancel / `failure_class` |
| Domain plane | Code / Git | File + Postgres RO data |

Narrative line for interviews / docs:

> Two Agent platforms, one governance philosophy: RepoPilot for engineering change; this repo for enterprise data analysis and data-plane policy.

---

## 4. Recommendation before M4

**Decision (2026-07-22): stay frozen — no M4 coding.**

1. Operate in [STABLE_PHASE.md](STABLE_PHASE.md): Demo / docs / regression.  
2. Do not reopen M1–M3 stop-lines.  
3. If a future phase is ever needed, re-rank from [M4_VALUE_RANKING.md](../roadmap/M4_VALUE_RANKING.md) with an explicit platform-value case.

---

## One-line story verdict

> M1–M3 already form a complete **Enterprise Data Agent Platform** Demo: Skill + Policy + Governed Run + Multi-plane data — without needing a Connector Framework or a second Skill.
