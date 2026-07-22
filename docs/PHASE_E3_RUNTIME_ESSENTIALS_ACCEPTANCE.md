# Phase E3 — Runtime Essentials Acceptance

**Status:** ✅ **Frozen** — see [PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md](./PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md)  
**Era:** 3 — Production Readiness (narrow)  
**Coding authorized:** 2026-07-22 · **Frozen:** 2026-07-22  

## Scope delivered (P0 only)

| ID | Capability | Behavior |
|----|------------|----------|
| E3.1 | Stale `running` reclaim | → `failed` + `failure_class=runtime_reclaimed` |
| E3.2 | Global in-flight limit | Reject enqueue (429) + defer claim / requeue |
| E3.3 | Queue depth guard | Reject enqueue when `LLEN >= max` (429) |

**Heartbeat:** optional freshness via `last_heartbeat_at` (not a lease).  
**Out of this freeze:** workspace concurrency · `replay_of`

## Principles kept

- Lifecycle in Worker / `task_service` only  
- Kernel / Skill / Policy / Trace / Artifact contracts unchanged (additive only)  
- Redis List retained  

## Config

| Setting | Default | Env |
|---------|---------|-----|
| `run_max_in_flight` | 4 | `RUN_MAX_IN_FLIGHT` |
| `analysis_queue_max_depth` | 50 | `ANALYSIS_QUEUE_MAX_DEPTH` |
| `stale_running_seconds` | 0 → timeout+60 | `STALE_RUNNING_SECONDS` |
| `run_heartbeat_interval_seconds` | 15 | `RUN_HEARTBEAT_INTERVAL_SECONDS` |

## Proof

```text
backend/scripts/smoke_e3_runtime_essentials.py
```

## Non-goals (still frozen)

auto-retry · resume · Celery/Kafka/Streams · scheduler · FinOps · hard-kill · workspace concurrency · replay_of  

## Related

- [PHASE_E3_RUNTIME_ESSENTIALS_CHECKLIST.md](./PHASE_E3_RUNTIME_ESSENTIALS_CHECKLIST.md)  
- [PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md](./PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md)  
- Next ranking: [ERA_3_NEXT_VALUE_RANKING.md](./ERA_3_NEXT_VALUE_RANKING.md)  
