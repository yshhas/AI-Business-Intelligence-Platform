# Next Candidates — Design Only (post E2 freeze)

**Status:** Observation window **formally OPEN** — sole log [OBSERVATION_LOG.md](./OBSERVATION_LOG.md). No coding until evidence packet + authorize.
**Date:** 2026-07-22  
**Context:** E1-AC frozen · E2 Explainability frozen. **Observation window active.**  
**Tech review / go-no-go:** [STAGE_RETROSPECTIVE_TECH_REVIEW.md](./STAGE_RETROSPECTIVE_TECH_REVIEW.md)  
**Active log:** [OBSERVATION_LOG.md](./OBSERVATION_LOG.md) — append dated evidence; do not start C2–C4 without Go.

**Architecture lock:**

```text
Skill → Policy → Data Plane → Trace
Product Shell: Permission · Budget · Analyze explainability
```

---

## 0. Decision posture

| Do now | Do not |
|--------|--------|
| Observe E1 `link_*` rates + Demo understanding of E2 | Start Repair / Connector / Cost by default |
| Collect demand evidence before picking a knife | Bundle multiple themes in one PR |
| Keep Eval `allow_heuristic_sql=false` | Soften Gate / rewrite Kernel |

**Valid choice:** **Hold — observe only** until signals clarify.

---

## 1. Ranked next candidates (design)

### Candidate C1 — Hold / observation toolkit (thin, optional)

**Why:** User priority is *watch Linking + E2 value + demand evidence* before building.

| | |
|--|--|
| **Problem** | Quality reports exist; comparing runs over time is still manual |
| **Value** | Supports Repair / Cost go-no-go without product sprawl |
| **Approach** | Optional: document operator recipe to diff two `evals/reports/*.json` **or** tiny `scripts/eval_diff.py` (rates + case pass only) |
| **Not** | Eval SaaS, dashboards, LLM-as-Judge, expanding N2 into a platform |
| **When** | Only if observation is painful enough to block decisions |

Default recommendation: **prefer Hold with manual JSON compare** before any script.

---

### Candidate C2 — E3 Cost display (thin)

| | |
|--|--|
| **Problem** | Soft budget rejects enqueue; Analyze rarely shows used vs budget |
| **Value** | Closes P0-2 observe loop; pairs with existing `llm_total_tokens` on Run |
| **Approach** | Read API: workspace UTC-day tokens used (+ configured budget); one line on Analyze/Tasks; reuse E2 Resources card |
| **Not** | FinOps, invoices, model router, multi-currency |
| **Open if** | Operators hit 429/budget_rejected repeatedly **and** cannot explain spend from Task tokens alone |

---

### Candidate C3 — E1-B SQL Repair (evidence-gated)

| | |
|--|--|
| **Problem** | Post-link Gate/execute failures retry with unstructured `gate_error` paste |
| **Value** | Measurable recovery **only if** failures cluster after successful linking |
| **Approach** | Closed `repair_class` enum + structured hint on **existing** retry edges; Trace counts; Eval cases |
| **Forbidden** | ReAct, free planner, silent retry expansion, Gate softening |
| **Open only if** | Eval/live Trace show classifiable post-link failures; linking not the dominant miss; expected yield documented |

Shelf design: [PHASE_E1_SQL_QUALITY_CHECKLIST.md](./PHASE_E1_SQL_QUALITY_CHECKLIST.md) §B.

---

### Candidate C4 — E4 Connector Lite (trigger-gated)

| | |
|--|--|
| **Open only if** | Named third RO source + charter |
| **Approach** | Thin executor protocol behind same Policy Gate |
| **Not** | Connector marketplace, CDC, writes |

---

### Candidate C5 — E2 polish (micro) — **low priority**

| | |
|--|--|
| **Examples** | Tasks list chips for failure_class/tokens; i18n copy only |
| **Risk** | Scope creep into Explorer |
| **Verdict** | Only if Demo feedback is specific and tiny; else skip |

---

## 2. Suggested sequence after observation

```text
[Observe E1 metrics + E2 Demo feedback + demand]
        │
        ├─► Hold (default) until evidence
        ├─► C2 Cost display     if budget pain is clear
        ├─► C3 SQL Repair       if post-link failure clusters prove yield
        ├─► C1 eval_diff lite   if manual compare blocks decisions
        └─► C4 Connector        only with named source
```

---

## 3. Human decision gate

| Option | Meaning |
|--------|---------|
| **Hold — observe only** | **Recommended default**; revisit with metrics/feedback notes |
| **Authorize C2 (Cost)** | Requires written budget-pain evidence |
| **Authorize C3 (Repair)** | Requires Eval/Trace failure-cluster summary |
| **Authorize C1 (eval_diff)** | Only if observation tooling is the bottleneck |
| **Authorize C4 (Connector)** | Named source + charter required |

---

**This document does not authorize coding.**
