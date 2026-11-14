# E2 Acceptance — Trace / Analyze Explainability

**Status:** ✅ **FROZEN** (human-confirmed 2026-07-22) — see [PHASE_E2_FINAL_STATUS.md](PHASE_E2_FINAL_STATUS.md)  
**Checklist:** [PHASE_E2_EXPLAINABILITY_CHECKLIST.md](PHASE_E2_EXPLAINABILITY_CHECKLIST.md)  
**Positioning:** Analyze **result explainability layer** — not a Trace Explorer.

---

## Constraints honored

| Constraint | Result |
|------------|--------|
| No Kernel / Worker / Policy / Data Plane changes | Pass |
| No new Trace storage / no duplicated execution model | Pass — API field pass-through only |
| No new aggregation service | Pass |
| Facts from existing fields only | Pass — sql_quality, steps, policy_decisions, authorization, artifacts/lineage, llm_total_tokens |
| No Chat / Streaming / LLM viz / LangSmith | Pass |
| N2 CLI not built | Pass — first-fail step label reuse only |
| `fallback_full` / deny / failure shown honestly | Pass (smoke + UI tones) |

---

## Changed files

| Path | Change |
|------|--------|
| `backend/app/schemas/task.py` | `ExecutionTraceOut.sql_quality` |
| `backend/scripts/smoke_e2_explainability.py` | **NEW** |
| `backend/scripts/smoke_release_gate.py` | Wire E2 smoke |
| `frontend/src/types/task.ts` | `sql_quality` on ExecutionTrace |
| `frontend/src/lib/traceLabels.ts` | **NEW** — labels / helpers |
| `frontend/src/components/ExecutionTracePanel.tsx` | Explainability strip + authz + policy |
| `frontend/src/components/ArtifactsPanel.tsx` | Pipeline hint + collapsed JSON |
| `frontend/src/components/TaskResultPanel.tsx` | Link note under SQL + tokens |
| `frontend/src/pages/AnalyzePage.tsx` | Header chips, steps labels, 429 copy |
| `frontend/src/pages/TasksPage.tsx` | Pass steps/tokens into panels |
| `docs/PHASE_E2_*` | Checklist + acceptance |

---

## Smoke / verification

```text
smoke_e2_explainability.py → E2_EXPLAINABILITY_OK
  - ExecutionTraceOut preserves sql_quality (incl. fallback_full)
  - authorization + policy deny reason present
frontend build (tsc + vite) → expected green after TS fixes
```

---

## UI (what a user sees on one Run)

1. **Task header** — status, failure_class label, skill@version, plane, tokens  
2. **Run explainability** — four cards: Schema used · Why this SQL · Policy · Resources  
3. **Authorization** — role, authorized tables, ACL mode  
4. **Policy / tools / artifact refs** — deny reason prominent  
5. **First failure** — derived from steps (light N2 reuse)  
6. **Artifacts** — production path hint + lineage; raw JSON collapsed  
7. **SQL** — link_status note (fallback not silent)  
8. **Steps** — human labels; Details for link / Gate / generate  

---

## Release gate impact

| Addition | Blocking? |
|----------|-----------|
| `smoke_e2_explainability` | **Yes** (in core smoke list) |
| Existing smokes | Unchanged |

Gate slightly longer; no Eval suite change in E2.

---

## Explicitly out of scope (still)

- Trace Explorer product  
- SQL Repair UI  
- N2 Eval CLI  
- Chat / token streaming / LangSmith  
