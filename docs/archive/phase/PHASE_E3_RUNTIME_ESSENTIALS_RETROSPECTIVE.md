# Phase E3 — Runtime Essentials Freeze + Retrospective

**Status:** ✅ **Formally closed / frozen** (2026-07-22)  
**Slice:** Era 3 P0 only (E3.1–E3.3)

## Narrative completed

```text
M2:  Run can be governed (timeout / cancel / failure_class)
E3:  Run execution has capacity & crash honesty
     reclaim · in-flight limit · queue depth guard
```

**Proof (not a job platform):**
> Agent Runtime 从「能执行」升级为「在 Worker 异常与负载压力下仍有可信容量边界」——背压明确（429），不静默无限排队。

## Freeze (do not expand now)

| Keep | Do not |
|------|--------|
| `failed` + `runtime_reclaimed` | New terminal statuses for reclaim |
| Heartbeat as stale freshness only | Lease / fencing / distributed lock product |
| Redis List + `LLEN` depth guard | Celery / Kafka / Streams rewrite |
| Enqueue 429 reject | Wait/block enqueue under capacity |
| Worker / `task_service` ownership | Kernel lifecycle |
| Additive settings + `last_heartbeat_at` | Auto-retry / resume / scheduler / FinOps / hard-kill |

**Deferred (explicitly out of this freeze):** workspace concurrency · `replay_of`

M1–M6 contracts remain frozen. E3 P0 does not reopen Skill / Policy / Trace / Artifact models.

---

## Retrospective

### 1. From “can execute” to “has capacity boundaries”

| Before E3 | After E3 P0 |
|-----------|-------------|
| Worker crash → eternal `running` | Reclaim → terminal + `runtime_reclaimed` |
| Unbounded concurrent claim (multi-worker) | Global `run_max_in_flight` |
| Unbounded LPUSH | `analysis_queue_max_depth` → 429 |
| Capacity failure = silent backlog | Capacity failure = **explicit backpressure** |

This is **ops honesty**, not feature surface area — aligned with Era 3 positioning.

### 2. Design choices that held

| Choice | Why it was right |
|--------|------------------|
| Reclaim → `failed` (not new status) | Keeps terminal model small; filters already understand `failed` |
| Heartbeat ≠ lease | Enough for stale TTL; avoids cluster-lock theater |
| Reject enqueue (not wait) | Enterprise Runtime needs clear “no” under load |
| Claim defer + requeue | Necessary after BRPOP without inventing a new broker |
| Lifecycle stays in Worker | Kernel remains Skill dispatch only |

### 3. Remaining runtime limitations (accepted)

| Limitation | Note |
|------------|------|
| Cooperative timeout/cancel | Still not hard-kill of LLM/DuckDB |
| BRPOP then crash before claim | Rare; reclaim/pending paths cover most orphans |
| Global caps only | No per-workspace fairness yet (deferred) |
| No replay lineage | Operator re-runs manually as new task |
| No auto-retry | Intentional — Trace/Artifact identity |
| Single List semantics | At-most-once after pop; multi-worker is ops pattern |

Do **not** chase these with more Runtime complexity in the next slice unless production evidence forces a thin fix.

### 4. What not to do next in Runtime

Further Runtime work (priority queues, Streams, resume, FinOps) would **raise complexity** faster than enterprise credibility. Prefer other Era 3 themes first.

### 5. Suggested next Era 3 themes (ordering later)

After this freeze, value-rank (design only):

1. **Deployment hygiene** — config matrix, health, smoke-as-gate, structured logs  
2. **Skill lifecycle lite** — version pin / enable — still no Skill Store  
3. Runtime deferred items (workspace cap / `replay_of`) — only if multi-tenant pressure appears  

See [ERA_3_NEXT_VALUE_RANKING.md](../era/ERA_3_NEXT_VALUE_RANKING.md).

---

## Related

- [PHASE_E3_RUNTIME_ESSENTIALS_ACCEPTANCE.md](PHASE_E3_RUNTIME_ESSENTIALS_ACCEPTANCE.md)  
- [PHASE_E3_RUNTIME_ESSENTIALS_CHECKLIST.md](PHASE_E3_RUNTIME_ESSENTIALS_CHECKLIST.md)  
- [ERA_3_RUNTIME_PRODUCTION_READINESS_VALUE.md](../era/ERA_3_RUNTIME_PRODUCTION_READINESS_VALUE.md)  
