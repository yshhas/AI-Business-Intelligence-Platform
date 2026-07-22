# After Foundation — transition note

**Status:** Era 1 + Era 2 frozen · Era 3 P0 + Deployment Hygiene **frozen** (2026-07-22)

Operator bring-up and release gate: **[OPS_RUNBOOK.md](./OPS_RUNBOOK.md)**  
DH retro: [PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md](./PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md)

```powershell
# Full stack (API + Worker + deps)
docker compose -f docker/docker-compose.yml --env-file .env up -d --build

# Or infra-only + host smokes
docker compose -f docker/docker-compose.yml up -d postgres redis postgres_ro
cd backend
.\.venv\Scripts\python.exe scripts\smoke_release_gate.py
```

CI mirrors the gate on PR/push: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) (T-13).

---

## Foundation arc (complete)

```text
M1: Platform + Skill
M2: Governed Runtime
M3: Governed Data Plane
```

## Capability arc (complete)

```text
M4: Execution Trace
M5: Thin Permission
M6: Artifact Entity
```
