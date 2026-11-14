# Phase E3 — Runtime Essentials Checklist（design only）

**Status:** ✅ **Frozen** — see [PHASE_E3_RUNTIME_ESSENTIALS_ACCEPTANCE.md](PHASE_E3_RUNTIME_ESSENTIALS_ACCEPTANCE.md) · [PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md](PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md)  
**Era:** 3 — Production Readiness (narrow)  
**Prerequisite:** Era 1–2 frozen · [ERA_3_RUNTIME_PRODUCTION_READINESS_VALUE.md](../era/ERA_3_RUNTIME_PRODUCTION_READINESS_VALUE.md) accepted  
**Theme:** Credible Agent Runtime under crash / capacity pressure — **not** new product surfaces  

**Coding:** ✅ P0 delivered & frozen. Optional E3.4/E3.5 remain deferred.

---

## 0. Positioning

```text
Era 1–2:  Skill → Policy → Run → Plane → Trace → Permission → Artifact
Era 3:    Make Run execution trustworthy when the Worker / queue misbehaves
```

> Era 3 不扩展平台表面能力；只补齐 **Agent Runtime 在真实运行环境中的可信边界**。

### Confirmed principles (must keep)

| # | Principle |
|---|-----------|
| **P1** | Run lifecycle ownership stays in **Worker / `task_service`** — **never** moves into Kernel |
| **P2** | M1–M6 contracts unchanged: Skill / Tool / Policy / Trace / Artifact / Permission — Era 3 only adds **runtime governance** around Runs |
| **P3** | Keep **Redis List** queue; no Streams / Celery / Kafka rewrite |
| **P4** | Replay (if any) = **new Run** + optional lineage; never in-place resume |

---

## 1. Confirmed scope

### 1.1 P0 — Must (Runtime essentials)

| ID | Capability | Intent |
|----|------------|--------|
| **E3.1** | **Stale `running` reclaim** | Worker crash / abandon must not leave eternal `running` |
| **E3.2** | **Global in-flight limit** | Hard capacity boundary on concurrent executing Runs |
| **E3.3** | **Queue depth / enqueue guard** | Bound backlog; refuse or classify overflow honestly |

**Heartbeat:** Allowed only as an **implementation option** for E3.1 (e.g. `last_heartbeat_at` to refine staleness). **Out:** distributed lease fencing, lock servers, multi-region lease products.

### 1.2 Optional (same phase only if cheap)

| ID | Capability | Intent |
|----|------------|--------|
| **E3.4** | Per-workspace concurrency limit | Fairness across workspaces |
| **E3.5** | `replay_of` lineage | New Run records source `run_id`; execute fresh — **no** resume |

### 1.3 Explicit non-goals (frozen out)

| Do not |
|--------|
| Auto-retry / silent re-execute same `task_id` |
| Checkpoint / mid-graph resume |
| Celery / Kafka / Redis Streams queue rewrite |
| Priority / fair-share scheduler product |
| Token / FinOps / cost ledger |
| Hard-kill LLM / DuckDB / Postgres mid-query |
| Multi-Agent · IAM · Connector Framework · Marketplace |
| Kernel lifecycle APIs · M1–M6 contract breaks |
| Large platform refactor |

---

## 2. Architecture invariants

```text
Product Shell (enqueue guard, caps)
        |
Worker / task_service     ← OWN lifecycle, reclaim, in-flight accounting
        |
Redis List (unchanged)    ← still LPUSH / BRPOP
        |
Kernel.run                ← untouched Skill dispatch
        |
Skill → Tool → Policy → Data Plane
        |
Trace / Artifact          ← still materialize on terminals (incl. reclaim terminals)
```

| Layer | May change in E3 | Must not |
|-------|------------------|----------|
| Worker | Reclaim sweeper, heartbeat optional, slot accounting | Become Celery |
| `task_service` / API | Enqueue refuse; optional replay create | New IAM |
| `analysis_tasks` | Optional columns: heartbeat, `replay_of` | Rename to job platform |
| Redis | Same list key / pattern | New broker |
| Kernel / Skill / Policy | — | Any rewrite |
| Trace / Artifact | New `failure_class` values if needed | Schema religion / CMS |

---

## 3. Design detail (P0)

### 3.1 E3.1 — Stale `running` reclaim

**Problem:** After BRPOP + claim, process death leaves `status=running` forever → Trace/UI lie.

**Target behavior**

| Condition | Action |
|-----------|--------|
| `status=running` AND stale beyond threshold | Move to terminal (`failed` or `timed_out` — pick one rule and document) |
| Set `failure_class` | e.g. `worker_lost` / `stale_running` (name TBD in impl) |
| Trace / Artifacts | Best-effort materialize like other failure paths; incomplete OK |

**Staleness signal (choose at impl time)**

| Option | Pros | Cons |
|--------|------|------|
| A. `started_at` + fixed TTL only | Simplest | Long legitimate Runs need TTL ≥ max timeout |
| B. Optional heartbeat refreshed by Worker | Accurate | Slightly more code — **still not a lease product** |

**Rule:** TTL must be **≥** configured max Run timeout (+ grace). Prefer documenting Option A as default; B only if A false-positives.

**Who runs reclaim:** Worker loop tick **or** tiny periodic sweeper in same Worker process — not a new microservice.

### 3.2 E3.2 — Global in-flight limit

**Problem:** Unbounded concurrent `running` (multi-worker or future scale) exhausts host / DB.

**Target behavior**

| Point | Behavior |
|-------|----------|
| Claim time and/or enqueue time | If `count(status=running) ≥ MAX_IN_FLIGHT` → do not claim / or do not enqueue |
| Honesty | Clear error or leave `pending` until slot free (pick one; prefer **explicit reject at enqueue** or **skip claim + requeue** — decide in impl notes, keep simple) |
| Config | Env / settings: `RUN_MAX_IN_FLIGHT` (name TBD) |

**Keep:** Single Redis List; N worker processes optional (ops), each respects global count via DB.

### 3.3 E3.3 — Queue depth / enqueue guard

**Problem:** LPUSH without bound → Redis/memory/ops backlog.

**Target behavior**

| Point | Behavior |
|-------|----------|
| Before `enqueue_task` | If `LLEN(queue) ≥ MAX_DEPTH` → reject create/enqueue |
| API | Stable error (e.g. 429/503) + message; optional `failure_class` only if task row created then failed — prefer **fail before row** or mark `failed`+`enqueue_rejected` consistently |
| Config | `ANALYSIS_QUEUE_MAX_DEPTH` (name TBD) |

**Keep:** Redis List; `LLEN` is enough — no Streams.

---

## 4. Optional design (E3.4 / E3.5)

### 4.1 E3.4 — Workspace concurrency

- Count `running` (and optionally `pending`) per `workspace_id`
- Enforce at enqueue (aligns with M5 Product Shell)
- Config: `RUN_MAX_IN_FLIGHT_PER_WORKSPACE`

### 4.2 E3.5 — `replay_of`

- New task row; `replay_of = source_run_id` (nullable UUID column or platform metadata)
- Full new execution; new Trace / Artifact identities
- **No** copy of mid-flight state; **no** auto-chain retries

---

## 5. Acceptance criteria (Definition of Done — when coding later)

### P0

- [x] Crashed Worker leaving `running` is reclaimed to a **terminal** within configured TTL  
- [x] Reclaimed Run has honest `failure_class` (`runtime_reclaimed`) + Trace incompleteness OK  
- [x] Global in-flight cap prevents unbounded concurrent execution  
- [x] Queue depth guard prevents unbounded LPUSH backlog  
- [x] Redis List retained (no new broker)  
- [x] Kernel / Skill / Policy / Trace schema / Artifact contracts unchanged (additive columns only)  
- [x] Lifecycle logic remains in Worker / task_service only  
- [x] Smoke: reclaim · cap · depth-guard paths  
- [x] M1–M6 regression posture retained (M2/M6 smokes exercised at delivery)

### Optional (if in scope)

- [ ] Workspace cap enforced at enqueue  
- [ ] Replay creates new Run with `replay_of` set; distinct Artifact ids  

### Must remain false

- [ ] No auto-retry loop  
- [ ] No checkpoint resume  
- [ ] No Celery/Kafka/Streams  
- [ ] No priority scheduler / FinOps / hard-kill  

---

## 6. Implementation steps (gated — do not start yet)

| Step | Deliverable | Gate |
|------|-------------|------|
| **E3.0** | This checklist confirmed for coding | Human “go” |
| **E3.1** | Stale reclaim (+ optional heartbeat) | After E3.0 |
| **E3.2** | Global in-flight limit | After E3.0 |
| **E3.3** | Queue depth enqueue guard | After E3.0 |
| **E3.4** | Workspace cap (optional) | Explicit include |
| **E3.5** | `replay_of` (optional) | Explicit include |
| **E3.6** | Smoke + acceptance + freeze | — |

### Open points — **frozen for P0 implementation**

1. Reclaim terminal: **`failed` + `failure_class=runtime_reclaimed`**  
2. Staleness: **`coalesce(last_heartbeat_at, started_at)`** — heartbeat optional freshness only  
3. At capacity: **reject enqueue (429)**; claim defer + requeue if already dequeued  
4. E3.4 / E3.5: **out of first coding slice**

---

## 7. Decision gate

| Decision | Meaning |
|----------|---------|
| **Approve checklist (design)** | Boundaries locked; still **no code** |
| **Authorize coding** | Separate explicit message after open points chosen |
| **Stay frozen** | Do not implement; ops Docs only |

**Current request fulfillment:** design checklist only. **Await “authorize coding” before any implementation.**

---

## 8. Related

- [ERA_3_PLATFORM_MATURITY_REVIEW.md](../era/ERA_3_PLATFORM_MATURITY_REVIEW.md)  
- [ERA_3_RUNTIME_PRODUCTION_READINESS_VALUE.md](../era/ERA_3_RUNTIME_PRODUCTION_READINESS_VALUE.md)  
- [PHASE_M2_RETROSPECTIVE.md](PHASE_M2_RETROSPECTIVE.md)  
- [ERA_1_ERA_2_SUMMARY.md](../era/ERA_1_ERA_2_SUMMARY.md)  

## 9. One-line summary

> **E3 Runtime Essentials** = reclaim stuck Runs + bound in-flight + bound queue — Worker-owned, Redis List kept, M1–M6 contracts untouched — no retry/resume/job-platform rewrite.
