# Era 3 Candidate — Runtime Production Readiness (Value Assessment)

**Document type:** Design-only value / boundary review  
**Status:** Assessment — **no coding · no Phase · Era 3 not started**  
**Date:** 2026-07-22  
**Parent:** [ERA_3_PLATFORM_MATURITY_REVIEW.md](./ERA_3_PLATFORM_MATURITY_REVIEW.md)  
**Frozen baseline:** M2 Run lifecycle · Redis List Worker · cooperative timeout/cancel · no auto-retry  

---

## 0. Intent

After Era 1–2 freeze, leadership agrees:

> Next emphasis is **Production Readiness & platform credibility**, not new business capability.

This note **narrows only Runtime Production Readiness** into:

| Must ask | Answer form |
|----------|-------------|
| What is truly Enterprise-necessary? | Ranked essentials |
| What is overbuild? | Explicit reject list |
| What can wait? | Deferred / trigger-gated |
| Does this justify starting Era 3? | Decision gate (not a Phase checklist) |

**Scope in:** concurrency · queue reliability · resource budget · recovery / replay  
**Scope out:** Deployment Hygiene (companion doc later) · Skill Lifecycle · Policy Framework · second Skill  

---

## 1. As-is Runtime (ground truth)

```text
API enqueue → Redis List (LPUSH)
Worker loop → BRPOP → claim pending→running (CAS)
         → thread + soft timeout / cancel poll
         → terminal: succeeded | failed | cancelled | timed_out
         → Trace + Artifacts materialize on terminal paths
```

| Asset | Today |
|-------|--------|
| Queue | Single Redis List; at-most-once after BRPOP (message gone) |
| Concurrency | Effectively **1 Run per worker process** (serial `process_task`) |
| Timeout / cancel | Cooperative; documented limitation (not process isolator) |
| Retry | None by design (“new Run = new task”) |
| Crash while `running` | Task can remain **stuck `running`** until human intervention |
| Budgets | Per-Run `timeout_seconds` + SQL default limit; no workspace caps |

**Credibility gap (honest):** Demo governance is strong; **operator failure modes** (crash, backlog, noisy neighbor) are weak.

---

## 2. Evaluation criteria

| Criterion | Weight | Meaning |
|-----------|--------|---------|
| **E** Enterprise necessity | 40% | Without it, real multi-user / long-running ops lose trust |
| **H** Honesty with Trace/Artifact | 25% | Must not blur Run identity or silent mutation |
| **C** Continuity | 20% | Worker/Shell only; no Kernel/Celery rewrite |
| **T** Thin-slice feasibility | 15% | One design phase → small implementation later |

Drift risk scored separately: **Reject if risk ≥ 4** unless necessity is extreme.

---

## 3. Topic deep-dives

### 3.1 Concurrency model

| Question | Assessment |
|----------|------------|
| Problem | One worker = global serialization; multi-workspace Demo still “feels” single-tenant ops |
| Enterprise need | **Medium–High** once >1 analyst or long SQL Runs coexist |
| Continuity | Cap in Worker / enqueue path — **high** |
| Overbuild | Multi-queue sharding, priority queues, fair-share schedulers, K8s HPA-as-product |

**Candidate thin slices**

| ID | Slice | Necessity | Honesty | Continuity | Verdict |
|----|-------|-----------|---------|------------|---------|
| C1 | **Global max in-flight Runs** (config: worker slots or “refuse claim if N running”) | High | High | High | **Essential candidate** |
| C2 | **Per-workspace max in-flight / queued** | Medium | High | High | **Should-have** (after C1) |
| C3 | Multi-worker horizontal scale (N identical consumers on same List) | Medium | High | High | **Ops pattern**, not a feature Phase — document + optional compose profile |
| C4 | Priority / deadline scheduling | Low | — | Medium | **Overbuild now** |

**Recommendation:** Treat **C1 (+ document C3)** as the concurrency core. C2 if multi-tenant Demo pressure appears. Do not invent a scheduler product.

---

### 3.2 Queue reliability

| Question | Assessment |
|----------|------------|
| Problem | BRPOP removes ID immediately → worker crash after dequeue ⇒ Run orphaned or lost from queue while DB says `pending`/`running` |
| Enterprise need | **High** for “production readiness” narrative — stuck Runs destroy Trace trust |
| Continuity | Redis + Worker + `analysis_tasks` status — **high** |
| Overbuild | Kafka, Streams-as-rewrite, exactly-once, outbox frameworks |

**Failure modes (ranked)**

| Mode | Likelihood (Demo→prod) | Severity | Thin mitigation |
|------|------------------------|----------|-----------------|
| Worker dies while `running` | Medium | **High** | Stale reclaim: `running` + `started_at` older than TTL → `failed`/`timed_out` + `failure_class=worker_lost` (name TBD) |
| BRPOP then crash before claim | Low–Medium | Medium | Prefer **claim-before-ack** pattern *or* re-queue on crash — careful with duplicates |
| Redis down | Low–Medium | High | Enqueue fail already; health gate (Deployment Hygiene) |
| Duplicate process_task | Low | Medium | Existing CAS claim helps |

**Candidate thin slices**

| ID | Slice | Necessity | Honesty | Continuity | Verdict |
|----|-------|-----------|---------|------------|---------|
| Q1 | **Stale `running` reclaim / sweeper** | **Essential** | High if new terminal + Trace | High | **#1 Runtime essential** |
| Q2 | Heartbeat / `last_heartbeat_at` on running task | Medium | High | High | **Companion to Q1** (makes TTL accurate) |
| Q3 | Redis List → Streams with consumer group | Medium | — | **Low** (rewrite) | **Overbuild** vs Q1/Q2 |
| Q4 | Durable outbox / transactional enqueue | Low–Medium | — | Medium | **Defer** until dual-write pain is proven |

**Recommendation:** **Q1 (+ optional Q2)** close most enterprise credibility without leaving Redis List. Do **not** open Streams/Celery to fix orphans.

---

### 3.3 Resource budget

| Question | Assessment |
|----------|------------|
| Problem | One runaway Run can hold the only worker slot; SQL already partially limited |
| Enterprise need | **Medium** — timeout exists; budgets refine noisy-neighbor, not identity |
| Continuity | Settings + Worker + Policy/Tool limits — **high** |
| Overbuild | Token billing, cost center UI, FinOps product, GPU quotas |

**Layers already present**

- Run `timeout_seconds` / cooperative timeout  
- SQL default / max limit paths  
- Cancel  

**Candidate thin slices**

| ID | Slice | Necessity | Honesty | Continuity | Verdict |
|----|-------|-----------|---------|------------|---------|
| B1 | Enforce **workspace concurrent Run cap** at enqueue (403/429 + clear message) | Medium–High | High | High | **Should-have** (ties to C2) |
| B2 | Soft **queue depth limit** (reject enqueue) | Medium | High | High | **Should-have** with C1 |
| B3 | Per-Run wall-clock already | Done | — | — | Keep; document as budget v0 |
| B4 | LLM token / $ budget ledger | Low | Medium | Medium | **Overbuild** (one Skill, Demo LLM) |
| B5 | Guaranteed mid-query kill (DB cancel) | Low–Medium | — | Low–Medium | **Out** (M2 freeze: not process isolator) |

**Recommendation:** Budgets that matter now are **capacity budgets** (slots, queue depth, existing timeout)—not FinOps. Pair with concurrency; do not start a “budget platform.”

---

### 3.4 Run recovery / replay

| Question | Assessment |
|----------|------------|
| Problem | Operators want “try again” after timeout/connector blip; silent retry tempts product managers |
| Enterprise need | **Recovery of stuck state = High**; **automatic retry = Low–Negative** |
| Honesty | Silent retry **breaks** Trace/Artifact lineage (“which attempt is truth?”) |
| Continuity | New Run row is already the model |

**Modes**

| Mode | Description | Verdict |
|------|-------------|---------|
| **R0 Stuck recovery** | Sweeper closes orphan `running` (see Q1) | **Essential** (recovery ≠ replay) |
| **R1 Manual replay** | API/UI “Run again” → **new** `run_id`; optional `replay_of` link | **Should-have** (thin, honest) |
| **R2 Auto-retry N times** | Worker re-executes same task_id | **Reject** for default Era 3 |
| **R3 Checkpoint resume** | Continue LangGraph mid-flight | **Reject** (saga / Multi-Agent adjacent) |
| **R4 Exactly-once replay** | Dedupe side effects across planes | **Reject** (select-only helps, still overbuild) |

**Why auto-retry is overbuild here**

1. Trace already records policy denies / tool errors — retrying hides operator judgment  
2. Artifacts/UUIDs materialize per terminal Run — mutating in place confuses lineage  
3. M2 explicitly chose **no retry framework**  
4. Connector/LLM flakiness is better handled by **new Run** + clear `failure_class`  

**Recommendation:** Split language carefully:

- **Recovery** = make terminal truth for crashed workers (**Q1**) — essential  
- **Replay** = optional new Run with lineage link (**R1**) — valuable, small  
- **Retry engine** = do not build  

---

## 4. Consolidated ranking

### 4.1 Essential (Enterprise-necessary for Runtime credibility)

| Priority | Item | Closes |
|----------|------|--------|
| **1** | **Q1 Stale `running` reclaim** (+ optional Q2 heartbeat) | Orphan Runs / false “still running” |
| **2** | **C1 Global in-flight limit** | Single runaway / accidental overload |
| **3** | **B2 Queue depth limit** (or enqueue refuse) | Redis backlog unbounded growth |

These three are enough to argue “Production Readiness lite” without a job platform.

### 4.2 Should-have (thin, after essentials)

| Item | Note |
|------|------|
| C2 / B1 Per-workspace caps | Multi-tenant fairness |
| R1 Manual replay-as-new-Run | Operator UX; optional `replay_of` |
| C3 Document multi-worker | Ops scale-out without code drama |
| Failure_class for worker_lost / queue_full | Trace honesty |

### 4.3 Defer / trigger-gated

| Item | Trigger |
|------|---------|
| Redis Streams / consumer groups | Q1/Q2 proven insufficient under load |
| Transactional outbox | Documented dual-write incidents |
| Token/$ budgets | Cost incidents or multi-LLM Skills |
| Per-tool rate limits | Abuse or shared API quotas |

### 4.4 Overbuild (do not)

| Reject | Why |
|--------|-----|
| Celery / Kafka / Temporal rewrite | Disproportionate; breaks M2 “Redis List is enough” thesis |
| Silent auto-retry / in-place resume | Trace & Artifact identity |
| Priority / fair-share scheduler product | Premature optimization |
| Guaranteed hard-kill of LLM/DB | Honesty already documented as cooperative |
| Distributed lease fencing clusters | Ops theater for current scale |
| Exactly-once saga across planes | Select-only Domain doesn’t need it |

---

## 5. Relationship to Deployment Hygiene

Runtime essentials **assume** basic deploy signals (health, smoke). Recommended coupling (still design-only):

```text
Runtime Q1/C1/B2  ←→  health shows worker+redis+db
                   ←→  smoke proves enqueue→terminal→trace
```

Do **not** merge into one mega-Phase yet; keep boundaries:

| Pack | Owns |
|------|------|
| Runtime Production Readiness | Worker/queue/task state machine honesty |
| Deployment Hygiene | Config matrix, reproducibility, CI smoke gate, structured logs |

---

## 6. Does this justify starting Era 3?

| Signal | Implication |
|--------|-------------|
| Only need Demo polish / resume narrative | **Stay frozen** — essentials can wait |
| Real users / multi-workspace / fear of stuck `running` | **Narrow Era 3 opener** = Runtime essentials (Q1→C1→B2) |
| Want “enterprise” via IAM/CMS/Celery | **Wrong opener** — reject; re-read maturity review |

**Suggested decision (recommendation, not approval):**

> If Era 3 starts, **open with Runtime Production Readiness essentials only** — reclaim + capacity limits — **explicitly excluding** auto-retry, queue rewrite, and scheduler product.

**Boundaries confirmed → design checklist:** [PHASE_E3_RUNTIME_ESSENTIALS_CHECKLIST.md](./PHASE_E3_RUNTIME_ESSENTIALS_CHECKLIST.md)  
**Coding still gated** until checklist is explicitly authorized for implementation.

---

## 7. One-page summary

| Theme | Essential? | Overbuild? |
|-------|------------|------------|
| Concurrency caps | **Yes** (global; then workspace) | Priority schedulers |
| Queue reliability | **Yes** (stale running reclaim) | Streams/Celery rewrite |
| Resource budget | **Capacity + existing timeout** | FinOps / token ledger |
| Recovery | **Yes** (terminalize orphans) | — |
| Replay | Manual new Run = OK | Auto-retry / resume |

```text
Enterprise Runtime lite =
  honest terminals under crash
  + bounded concurrency / queue
  + replay = new Run
  ≠ job platform
```

---

## 8. Related

- [ERA_3_PLATFORM_MATURITY_REVIEW.md](./ERA_3_PLATFORM_MATURITY_REVIEW.md)  
- [PHASE_M2_RETROSPECTIVE.md](./PHASE_M2_RETROSPECTIVE.md)  
- [ERA_1_ERA_2_SUMMARY.md](./ERA_1_ERA_2_SUMMARY.md)  
