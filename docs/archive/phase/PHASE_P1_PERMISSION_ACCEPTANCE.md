# P1 Permission / Governance — Acceptance

**Status:** ✅ **Complete** (human confirmed 2026-07-22)  
**Date:** 2026-07-22  
**Lock:** [PHASE_P1_PERMISSION_IMPLEMENTATION_LOCK.md](PHASE_P1_PERMISSION_IMPLEMENTATION_LOCK.md)  
**Checklist:** [PHASE_P1_PERMISSION_GOVERNANCE_CHECKLIST.md](PHASE_P1_PERMISSION_GOVERNANCE_CHECKLIST.md)

## Goals achieved

- [x] Dataset ACL for asset access control  
- [x] ACL ↔ SQL Policy Gate responsibility split preserved  
- [x] Trace retains authorization context (audit only)  
- [x] No IAM suite; Kernel / Skill / Policy / Plane boundaries held  

## Delivered

| Item | Evidence |
|------|----------|
| Migration `dataset_acl` | `0011_p1_dataset_acl.py` |
| Compat default | No ACL rows ⇒ M5 role-only |
| Owner bypass | Implicit full read/run |
| Shell ACL helpers | `permissions.py` `can_read/run_dataset`, `can_access_task` |
| API | `GET/PUT .../datasets/{id}/acl` (owner); list/get/preview/run filtered |
| Trace authorization | `platform.authorization` in agent_runtime (audit only) |
| Frontend | Dataset list uses filtered API (no ACL admin UI) |
| Smoke | `smoke_p1_permissions.py` in release gate |

## Split (unchanged architecture)

- **ACL** — may the user access this Dataset / Run?  
- **Policy Gate** — may this SQL execute?  
- Kernel does **not** import RBAC.

## Next phase

**Enhancement Phase** (capability growth, not freeze-first):  
→ [ENHANCEMENT_ROADMAP.md](../roadmap/ENHANCEMENT_ROADMAP.md) (design only until item authorized).
