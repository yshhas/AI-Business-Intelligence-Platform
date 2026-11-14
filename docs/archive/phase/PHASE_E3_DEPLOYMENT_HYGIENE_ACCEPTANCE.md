# Phase E3 — Deployment Hygiene Acceptance

**Status:** ✅ **Frozen** — see [PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md](PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md)  
**Era:** 3 — Deployment Hygiene  
**Coding authorized:** 2026-07-22 · **Frozen:** 2026-07-22  

## Delivered

| ID | Item | Evidence |
|----|------|----------|
| DH.1 | Config matrix + `.env.example` | [OPS_CONFIG_MATRIX.md](../../ops/OPS_CONFIG_MATRIX.md) · `.env.example` |
| DH.2 | live / ready | `GET /health/live` · `GET /health/ready` (DB+Redis; 503 if not) |
| DH.3 | Release gate | `backend/scripts/smoke_release_gate.py` (M3 conditional) |
| DH.4 | Operator runbook | [OPS_RUNBOOK.md](../../ops/OPS_RUNBOOK.md) |
| DH.5 | Trace-aligned logs | `app/core/observability.py` + Worker / `task_service` |

## Decisions kept

- Worker: **docs only** (no Worker HTTP)  
- No Dockerfile  
- No GitHub Actions (script + docs)  
- M3 smoke: skip when `POSTGRES_RO_DSN` unset  

## Non-goals (still frozen)

APM/SIEM · new queue · Runtime deferred · contract changes · Worker HTTP · Dockerfile · Actions  

## Related

- [PHASE_E3_DEPLOYMENT_HYGIENE_CHECKLIST.md](PHASE_E3_DEPLOYMENT_HYGIENE_CHECKLIST.md)  
- [PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md](PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md)  
- [OPS_RUNBOOK.md](../../ops/OPS_RUNBOOK.md)  
