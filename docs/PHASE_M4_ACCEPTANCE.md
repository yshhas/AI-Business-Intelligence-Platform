# Phase M4 — Traceable Execution Model Acceptance

**Status:** ✅ **Frozen** — see [PHASE_M4_RETROSPECTIVE.md](./PHASE_M4_RETROSPECTIVE.md)  
**Era:** 2 — Enterprise Capability Enhancement  
**Prerequisite:** M1–M3 Foundation frozen  

## Proof

> Run 侧效应升级为可查询 **Execution Trace**（ToolCall / PolicyDecision / ArtifactRef），不是 Audit 产品。

## Delivered

| Item | Detail |
|------|--------|
| Converter | `agent/kernel/execution_trace.py` → `to_execution_trace()` |
| Facade | Merges `platform.execution` via converter (legacy projection unchanged) |
| Persist | JSON snapshot + columns `skill_id`, `source_type`, `policy_denied` |
| Partial fail | `AgentAnalysisError` carries partial `result_json` with execution |
| API | `GET .../tasks/{id}/execution`; `GET .../tasks` filters |
| UI | `ExecutionTracePanel` on Analyze + Tasks (no Audit Center) |

## Acceptance (freeze checklist)

- [x] Success path model: ToolCall / PolicyDecision / ArtifactRef in `platform.execution`  
- [x] Policy deny: reason + policy_id + call link; smoke OK  
- [x] Filters + `GET .../execution`  
- [x] No Audit Center / events table / SIEM  
- [x] Boundaries: Trace truth = `platform.execution` + thin columns  

Local E2E (operator): success Run Trace UI; deny reason; cancel/timeout incomplete; M1–M3 regression — assumed complete for freeze per product confirmation.

## Non-goals (confirmed out)

Audit Center · Audit microservice · Event sourcing · SIEM · log platform  

## Related

- [PHASE_M4_CHECKLIST.md](./PHASE_M4_CHECKLIST.md) · [PHASE_M4_RETROSPECTIVE.md](./PHASE_M4_RETROSPECTIVE.md)  
- Next: [PHASE_M5_CHECKLIST.md](./PHASE_M5_CHECKLIST.md) (design only)
