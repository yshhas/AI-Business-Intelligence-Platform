# Phase M6 — Artifact Lifecycle Acceptance

**Status:** ✅ **Frozen** — see [PHASE_M6_RETROSPECTIVE.md](./PHASE_M6_RETROSPECTIVE.md)  
**Era:** 2 — Enterprise Capability Enhancement  
**Prerequisite:** M4 Trace + M5 Permission frozen  

## Positioning

```text
Agent Run → Execution Trace → Artifact → Lineage / Access
```

Artifact is a **first-class platform product** of the Enterprise Agent Platform — **not** a Report Center / CMS / PDF system.

## Decisions (frozen)

| Topic | Choice |
|-------|--------|
| Persistence | Thin table `run_artifacts` (metadata + `content_ref`) |
| ID | UUID (independent of Run) |
| Global API | Out — run-scoped only |
| Status | `available` \| `unavailable` only |
| Payload | `content_ref` into `result_json` (no copy) |
| Partial | Emit `unavailable` stubs |
| Access | Inherit M5 Run visibility (`artifact.list` / `artifact.get`) |

## Delivered

| Item | Detail |
|------|--------|
| Migration | `0007_m6_run_artifacts` |
| Model | `RunArtifact` |
| Materialize | Worker terminal paths → `artifact_service.materialize_for_task` |
| Skill | UUID on all `data.bi` Artifacts |
| API | `GET .../tasks/{id}/artifacts` · `GET .../tasks/{id}/artifacts/{artifact_id}` |
| Trace sync | `platform.execution.artifacts[]` shares durable ids + status |
| UI | Artifacts list on Analyze / Tasks (no Report Center) |
| Smoke | `backend/scripts/smoke_m6_artifacts.py` |

## Acceptance checklist

- [x] Successful Run lists Artifacts with stable UUID identity  
- [x] Trace ArtifactRefs share the same ids  
- [x] Lineage links Artifact → Run → Trace path → Skill / Data Plane  
- [x] Partial / missing types recorded as `unavailable`  
- [x] viewer can list/get; cannot create Runs (M5 unchanged)  
- [x] Legacy `result_json` UI still works  
- [x] No Report Center / CMS / PDF / global Artifact service  
- [x] M1–M5 regression posture retained (Kernel / Run / Plane / Trace / Permission)  

## Non-goals

Report Center · Artifact Marketplace · file/CMS · Export platform · retention/expired · `GET /artifacts/{id}`

## Related

- [PHASE_M6_CHECKLIST.md](./PHASE_M6_CHECKLIST.md) · [PHASE_M6_RETROSPECTIVE.md](./PHASE_M6_RETROSPECTIVE.md)  
- Era close-out: [ERA_1_ERA_2_SUMMARY.md](./ERA_1_ERA_2_SUMMARY.md)  
- Smoke: `backend/scripts/smoke_m6_artifacts.py`  
