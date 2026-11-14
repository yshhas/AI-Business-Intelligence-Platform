# Phase M5 — Resource Permission (thin RBAC) Acceptance

**Status:** ✅ **Frozen** — see [PHASE_M5_RETROSPECTIVE.md](PHASE_M5_RETROSPECTIVE.md)  
**Era:** 2 — Enterprise Capability Enhancement  
**Prerequisite:** M4 frozen  

## Proof

```text
Agent Run → Execution Trace → Authorized Resource Access
```

Thin workspace+role gates — **not** IAM.

## Delivered

| Item | Detail |
|------|--------|
| Matrix | `backend/app/services/permissions.py` |
| Dataset | upload / bind_postgres_ro require owner\|analyst |
| Run | create requires mutator; list/get/execution/steps any member |
| Cancel | creator \| owner (unchanged) |
| Errors | 403 in-workspace; membership miss still 404 |
| UI | viewer: hide upload/bind; disable Analyze submit |
| Skill | `skill.invoke` reserved via `run.create` + `data.bi` |

## Acceptance (freeze)

- [x] viewer cannot upload / bind / create Run  
- [x] owner/analyst retain mutator capabilities  
- [x] No ACL tables / Invite / SSO  
- [x] Kernel untouched  
- [x] Trace access aligned with Run visibility  

## Non-goals

IAM · SSO · Invite · org management · per-dataset ACL · Kernel RBAC  

## Related

- [PHASE_M5_CHECKLIST.md](PHASE_M5_CHECKLIST.md) · [PHASE_M5_RETROSPECTIVE.md](PHASE_M5_RETROSPECTIVE.md)  
- Next: [PHASE_M6_CHECKLIST.md](PHASE_M6_CHECKLIST.md) / [PHASE_M6_ACCEPTANCE.md](PHASE_M6_ACCEPTANCE.md)
