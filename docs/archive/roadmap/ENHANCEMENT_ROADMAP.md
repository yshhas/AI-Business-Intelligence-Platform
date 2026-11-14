# Enhancement Phase Roadmap

**Document type:** Capability enhancement plan  
**Status:** Active roadmap — **E1-AC + E2 frozen**; observation window before next knife  
**Updated:** 2026-07-22  
**Decision basis (preferred over checklist thrash):** [STAGE_RETROSPECTIVE_TECH_REVIEW.md](../reviews/STAGE_RETROSPECTIVE_TECH_REVIEW.md)  
**Observation log (active):** [OBSERVATION_LOG.md](../reviews/OBSERVATION_LOG.md)

**Architecture lock (unchanged):**

```text
Skill → Policy → Data Plane → Trace
Product Shell: Permission · Budget · Analyze explainability
```

**Hard constraints:**

| Forbidden | Why |
|-----------|-----|
| RAG / ReAct / Multi-Agent | Conflicts with fixed Skill + Policy-before-execute |
| Kernel / Policy / Plane rewrite | Spine identity |
| Trace Explorer / Observability platform / LangSmith dual-track | E2 freeze |
| SQL Repair without Eval evidence | Expands retry boundary prematurely |
| Large platformization | Overbuild |

**Parents:** [PROJECT_IMPROVEMENT_PLAN.md](PROJECT_IMPROVEMENT_PLAN.md) · [PHASE_E1_AC_FINAL_STATUS.md](../phase/PHASE_E1_AC_FINAL_STATUS.md) · [PHASE_E2_FINAL_STATUS.md](../phase/PHASE_E2_FINAL_STATUS.md)

---

## 0. Where we are (2026-07-22)

| Layer | State |
|-------|--------|
| Platform spine | Proven |
| Ops honesty | Eval core + quality suites · soft token budget · capacity |
| Governance | Workspace role + Dataset ACL + Trace authorization |
| AI Skill quality | ✅ Linking + Eval quality **frozen** · ⏸ Repair evidence-gated |
| Product explainability | ✅ Analyze Run explainability **frozen (E2)** |
| Cost / Connector UX | Still thin / trigger-gated |

```text
Frozen
  P0-1 Eval · P0-2 Soft budget · P1 ACL
  E1-AC Schema Linking + Eval Quality
  E2 Analyze Explainability

Observation (no code required)
  link_ok_rate / fallback causes
  Does E2 improve operator understanding?
  Evidence for Cost · Repair · Connector?

Next knife
  Explicit authorize only — see PHASE_NEXT_CANDIDATES.md
  Default: Hold — observe only
```

---

## 1. Theme status board

| ID | Theme | State | Next |
|----|-------|-------|------|
| **E1-AC** | Linking + Eval quality | ✅ Frozen | Observe metrics |
| **E1-B** | SQL Repair | ⏸ Shelf | Evidence-gated |
| **E2** | Analyze explainability | ✅ Frozen | Do not expand into Explorer |
| **E3** | Cost / Eval trends | Design | Demand-gated |
| **E4** | Connector Lite | Design | Named-source gated |

```text
Enhancement order (updated)
  E1-AC  Linking + Eval Quality     ✅ FROZEN
  E2     Analyze explainability     ✅ FROZEN
  E1-B   SQL Repair                 ⏸ evidence-gated
  E3     Cost display + eval diff   demand-gated
  E4     Connector Lite             trigger-gated
```

---

## 2. Theme notes (short)

### E1 — Text-to-SQL Quality

- **A+C delivered:** `link_schema`, `platform.sql_quality`, quality suite in release gate.  
- **B deferred:** open only with classifiable post-link failure yield.  
- **Observe:** `link_ok_rate`, `fallback_full` realism, failure stage split.

### E2 — Analyze explainability ✅

- Run page answers: schema used · why SQL · policy · fail where · artifacts how.  
- Facts only from existing Trace/steps/artifacts/tokens.  
- **Frozen:** no Trace Explorer, no new storage, no LangSmith, no Chat/streaming.  
- Docs: [FINAL_STATUS](../phase/PHASE_E2_FINAL_STATUS.md) · [ACCEPTANCE](../phase/PHASE_E2_ACCEPTANCE.md)

### E3 — Ops visibility

Cost used/budget read + UI; optional eval report diff. Secondary until budget pain is clear.

### E4 — Connector Lite

Defer until named third RO source + charter.

---

## 3. Cross-cutting won't-build

| Idea | Verdict |
|------|---------|
| Trace Explorer / Audit Center / Observability SaaS | **No** (E2 freeze) |
| RAG / ReAct / Multi-Agent | **No** |
| SQL Repair by default | **No** |
| Hide `fallback_full` | **No** |
| Chat / token streaming | **No** |

---

## 4. Recommendation

| Choice | Rationale |
|--------|-----------|
| **Default: Hold — observe** | Need Linking metric trends + E2 Demo signal + demand proof |
| **Next build (if any)** | C2 Cost **or** C3 Repair — only with written evidence |
| **Avoid** | Reopening E2 scope; starting Repair “because E2 is done” |

**Human gate:** [PHASE_NEXT_CANDIDATES.md](../phase/PHASE_NEXT_CANDIDATES.md) §3.

---

## 5. Summary table

| ID | Theme | State | Priority now |
|----|-------|-------|--------------|
| **E1-AC** | Linking + Eval | ✅ Frozen | Observe |
| **E1-B** | Repair | ⏸ | Evidence |
| **E2** | Explainability | ✅ Frozen | Observe Demo value |
| **E3** | Cost / trends | Design | Demand |
| **E4** | Connector | Design | Trigger |

---

**Coding requires an explicit authorize after the observation window.**  
**Hold — observe only** is the recommended default.
