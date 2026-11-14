# Phase M5 — Freeze + Retrospective

**Status:** ✅ **Formally closed / frozen** (2026-07-22)

## Narrative completed

```text
M4: Execution Trace Model
M5: Authorized Resource Access (thin RBAC in Product Shell)
```

**Proof (not IAM):**
> Dataset / Data Plane / Run / Trace 访问由 workspace + role 统一约束；Kernel / Skill / Policy / Run Runtime 不感知 RBAC。

## Freeze (do not expand now)

| Keep | Do not |
|------|--------|
| `permissions.py` matrix | ACL 表 / per-dataset ACL |
| owner \| analyst \| viewer | IAM / SSO / Invite / org UI |
| 403 in-workspace · 404 cross-workspace | Kernel-side authorization |
| viewer read-only for mutate/run | Private Run / per-run ACL |

## Retrospective

### 1. Is workspace+role enough?

**Verdict: Yes for Era 2 M5.** Resource-level ACL deferred until multi-domain data complexity forces it.

### 2. Did authz break Trace?

**Verdict: No.** Trace visibility matches Run get (workspace members); mutate paths gated separately.

### 3. Next

~~M6 Artifact Lifecycle~~ → **done / frozen** ([PHASE_M6_RETROSPECTIVE.md](PHASE_M6_RETROSPECTIVE.md)).  
Era 2 closed — see [ERA_1_ERA_2_SUMMARY.md](../era/ERA_1_ERA_2_SUMMARY.md). Next route: discussion only.
