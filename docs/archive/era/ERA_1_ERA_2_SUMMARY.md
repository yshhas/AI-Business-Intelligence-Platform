# Era 1 & Era 2 — Closed Summary

**Date:** 2026-07-22  
**Status:** Both eras **formally closed** for delivery. Next roadmap is discussion-only until a new phase is confirmed.

---

## Era 1 — Platform Foundation (M0–M3)

**Claim proved:**

```text
Skill execution
    → Policy governed
    → Run lifecycle managed
    → Multiple data planes
```

> 可治理的 Data Agent Runtime（可 Demo）— 不是 BI 应用，不是 Connector 产品。

| Phase | Delivered | Freeze line |
|-------|-----------|-------------|
| **M0** | Charter + contracts | Platform identity locked |
| **M1** | Kernel · Skill · Tool · Policy · Artifact · `data.bi` | No second Skill / Code Agent / connector framework |
| **M2** | timeout / cancel / `failure_class` | Worker owns lifecycle; no Celery / auto-retry |
| **M3** | `file` + `postgres_ro` behind `execute_select` | Policy-first; no Catalog / ETL / writes |

**Assets to extend, not rebuild:** Kernel `run`, Skill `data.bi`, Policy `sql.select_gate`, Run terminals, Data planes.

**Docs:** [PHASE_M1_RETROSPECTIVE](../phase/PHASE_M1_RETROSPECTIVE.md) · [M2](../phase/PHASE_M2_RETROSPECTIVE.md) · [M3](../phase/PHASE_M3_RETROSPECTIVE.md) · [PLATFORM_CHARTER](../../architecture/PLATFORM_CHARTER.md)

---

## Era 2 — Enterprise Capability Enhancement (M4–M6)

**Claim proved:**

```text
Agent Run
    → Execution Trace
    → Authorized Resource Access
    → Platform Artifact (+ Lineage)
```

> 可上企业叙事的 Data Agent Platform（可追溯 · 可授权 · 产出可管）— 不做 Audit/IAM/CMS 套件。

| Phase | Delivered | Freeze line |
|-------|-----------|-------------|
| **M4** | `platform.execution` Trace + filters + Run Trace UI | Not SIEM / events table / Audit Center |
| **M5** | Thin `permissions.py` (workspace + role) | Not IAM / SSO / Invite / ACL tables |
| **M6** | `run_artifacts` metadata + UUID + content_ref + run-scoped API | Not Report Center / CMS / PDF / retention / marketplace |

**Architecture invariant kept:**

```text
Product Shell → Worker/Run Lifecycle → Kernel.run → Skill(data.bi)
  → Tool → Policy → Data Plane
```

Kernel still does not own RBAC, lifecycle, or connectors. Artifact payload stays in `result_json` via `content_ref`.

**Docs:** [PHASE_M4_RETROSPECTIVE](../phase/PHASE_M4_RETROSPECTIVE.md) · [M5](../phase/PHASE_M5_RETROSPECTIVE.md) · [M6](../phase/PHASE_M6_RETROSPECTIVE.md) · [ENTERPRISE_CAPABILITY_ROADMAP](../roadmap/ENTERPRISE_CAPABILITY_ROADMAP.md)

---

## Combined platform story (frozen surface)

| Layer | Meaning after M6 |
|-------|------------------|
| Platform / Kernel | Dispatch-only Agent runtime |
| Skill | `data.bi` (first Data Skill) |
| Run Governance | timeout / cancel / `failure_class` |
| Data Plane | Policy-gated `file` \| `postgres_ro` |
| Trace | `platform.execution` (Run-centric) |
| Permission | Workspace + role (Product Shell) |
| Artifact | Metadata entity + lineage to Run/Trace/Skill/Plane |

**Sibling framing:** RepoPilot = Engineering Agent; this repo = Data Agent — **no Code Agent**.

---

## Explicitly out (until a new era/phase confirms)

| Out |
|-----|
| Connector Framework / Catalog / ETL |
| Second Skill / Multi-Agent mesh |
| IAM / SSO / Invite org suite |
| Audit microservice / SIEM |
| Report Center / Artifact CMS / PDF Export farm |
| Global Artifact marketplace / retention product |
| Celery rewrite / distributed job platform |

---

## Next

**Freeze holds** for Era 1–2 and Era 3 slices completed so far:

| Slice | Status |
|-------|--------|
| Runtime Essentials P0 | ✅ Frozen |
| Deployment Hygiene | ✅ Frozen |

Next human step: **refresh Era 3 value ranking (design only)** — no coding until ranking + checklist are confirmed.  
See [PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md](../phase/PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md).
