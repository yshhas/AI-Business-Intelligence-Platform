# Phase E3 — Deployment Hygiene Checklist（design only）

**Status:** ✅ **Frozen** — see [PHASE_E3_DEPLOYMENT_HYGIENE_ACCEPTANCE.md](./PHASE_E3_DEPLOYMENT_HYGIENE_ACCEPTANCE.md) · [PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md](./PHASE_E3_DEPLOYMENT_HYGIENE_RETROSPECTIVE.md)  
**Era:** 3 — Deployment Hygiene  
**Prerequisite:** [PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md](./PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md) · [ERA_3_NEXT_VALUE_RANKING.md](./ERA_3_NEXT_VALUE_RANKING.md)  
**Theme:** Stable deliver & operate — **not** APM / SIEM / new Runtime machinery  

**Coding:** ✅ Delivered & frozen (DH.1–DH.5).

---

## 0. Positioning

```text
E3 P0:  Runtime has capacity + crash honesty
E3 DH:  Platform can be deployed, verified, and operated repeatably
```

> 从「架构上像企业平台」走向「可以稳定交付和维护」——不改变 Kernel / Skill / Policy / Run / Trace / Artifact 契约。

### Principles (must keep)

| # | Principle |
|---|-----------|
| **P1** | No Kernel / Skill / Policy / Trace / Artifact model changes (docs & ops only, or thin Product Shell endpoints) |
| **P2** | No new scheduler, queue broker, lifecycle states, or Runtime capacity features |
| **P3** | Observability aligns with existing **Run Trace** (`run_id` / `failure_class`) — does not replace it |
| **P4** | Prefer scripts + Compose + one health surface over new microservices |

### Frozen elsewhere (do not reopen)

workspace concurrency · `replay_of` · auto-retry/resume · Celery/Kafka/Streams · scheduler/FinOps · hard-kill · IAM · Connector Framework · Marketplace · Multi-Agent · Report Center/CMS

---

## 1. As-is (ground truth)

| Area | Today | Gap |
|------|-------|-----|
| Config | `.env` / `Settings` (pydantic) · `.env.example` | No single operator matrix of required vs optional; E3 caps undocumented in one place |
| Compose | `docker/docker-compose.yml` — Postgres / Redis / postgres_ro + healthchecks | App/Worker not containerized; no “release pin” doc |
| Health | `GET /health` — app ok + redis ping + registry ids | No DB readiness; no distinction liveness vs readiness; no Worker signal |
| Migrations | Manual `alembic upgrade head` | Not enforced as a gate in CI (no GitHub Actions yet) |
| Smokes | Per-phase scripts + `STABLE_PHASE.md` fragment | No single “release gate” script; E3/M4–M6 not always listed together |
| Logs | std logging in Worker | Little structured correlation with `run_id` / `failure_class` |
| Trace | First-class `platform.execution` | Logs and Trace not explicitly paired for operators |

---

## 2. Target outcomes (Definition of Intent)

| Outcome | Meaning |
|---------|---------|
| **Config clarity** | Operator knows required env vars per role (API / Worker / planes) |
| **Health honesty** | Probe answers “process up” vs “safe to take traffic / run Jobs” |
| **Verify before claim “up”** | Migration + curated smoke suite as release bar |
| **Reproducible Demo** | Documented pin: Compose images, alembic head, smoke command |
| **Structured ops signal** | Worker/API logs carry Run keys that match Trace filters |

**Non-outcome:** full APM, log warehouse, distributed tracing product, K8s operator.

---

## 3. Scope breakdown

### 3.1 DH.1 — Configuration management & env consistency

| In | Out |
|----|-----|
| Documented **config matrix** (name, default, required?, used by API/Worker) | Consul / Vault product / dynamic remote config |
| Align `.env.example` with E3 settings (`RUN_MAX_IN_FLIGHT`, queue depth, stale TTL, heartbeat) | Secrets manager SaaS |
| Optional: `GET /health` or `/ops/config` **non-secret** echo (env name + whether set) | Dump secrets / DSNs in responses |

**Deliverable (when coding):** `docs/OPS_CONFIG_MATRIX.md` (or section in README) + `.env.example` sync.

### 3.2 DH.2 — Health / readiness boundaries

| Probe | Intent | Suggested checks |
|-------|--------|------------------|
| **Liveness** | Process alive | HTTP 200 cheap (current `/health` core or `/health/live`) |
| **Readiness** | Safe for Demo traffic / enqueue | DB connect · Redis ping · (optional) alembic revision == head |

| In | Out |
|----|-----|
| Split or extend health: `live` vs `ready` | Worker HTTP server mandatory (may use file/heartbeat later — keep optional) |
| DB ping on readiness | Deep dependency graphs / multi-region |
| Report E3 capacity settings (non-secret) on ready payload | Calling reclaim from health |

**Open point (freeze at coding kickoff):** Worker readiness — (A) omit in DH v1, document “Worker is process not probe”; (B) thin `/health` only on API + Compose note that Worker must be running for Analyze.

**Recommendation:** **API live/ready in DH v1**; Worker remains process + log line on start (already has settings dump) — avoid second HTTP stack unless trivial.

### 3.3 DH.3 — Smoke / migration gate

| In | Out |
|----|-----|
| Single entry script e.g. `scripts/smoke_release_gate.py` or `scripts/run_release_smokes.ps1` | Flaky e2e browser suite as gate |
| Ordered: `alembic upgrade head` (or check current) → M1/M2/(M3 if DSN)/(M4–M6)/E3 P0 smokes | Mandatory full agent LLM path in CI |
| Document “gate must be green before Demo claim” | Blocking production CD product |

**Curated gate set (proposed)**

```text
alembic upgrade head / current == head
smoke_kernel_m1
smoke_m2_lifecycle          # needs Redis
smoke_m4_execution_trace
smoke_m5_permissions
smoke_m6_artifacts
smoke_e3_runtime_essentials # needs Redis
smoke_m3_connector          # optional if POSTGRES_RO_DSN set
```

### 3.4 DH.4 — Deployment reproducibility

| In | Out |
|----|-----|
| Pin notes: Compose image tags already used (`postgres:16-alpine`, `redis:7-alpine`) | Multi-env Terraform |
| One-page **Operator runbook**: up Compose → migrate → API → Worker → smoke gate | Full containerization of API/Worker as must-have (stretch) |
| Record alembic head revision in health/ready or smoke output | Immutable release registry SaaS |

**Stretch (optional if cheap):** Dockerfile for API+Worker — **not** required to close DH if runbook + gate are solid.

### 3.5 DH.5 — Structured observability (Trace-aligned)

| In | Out |
|----|-----|
| Worker log fields: `run_id`, `status`, `failure_class`, `skill_id` (when known) | OpenTelemetry full stack / Jaeger product |
| API create/cancel log lines with `run_id` | Replacing Trace UI |
| Document: “logs point to Trace; Trace is source of execution truth” | SIEM export pipeline |

**Rule:** Logs **correlate** to Trace; they do **not** become a second execution model.

---

## 4. Architecture invariants

```text
Compose (Postgres/Redis/postgres_ro)
        │
API  ── health live/ready ── Product Shell (unchanged contracts)
        │
Worker ── structured logs (run_id…) ── same lifecycle as E3 P0
        │
Smokes / alembic ── release gate (docs + script)
        │
Trace / Artifacts ── unchanged truth for execution / outputs
```

| Layer | May change | Must not |
|-------|------------|----------|
| Docs / scripts | Matrix, runbook, gate script | — |
| `/health*` | Split live/ready, DB check | Authz product |
| Logging | Extra structured keys | Event-sourcing rewrite |
| Kernel / Skill / Policy | — | Any change |
| Runtime caps / reclaim | — | Reopen E3 P0 freeze |

---

## 5. Acceptance criteria

- [x] Config matrix documents API/Worker/plane env vars including E3 P0 caps  
- [x] `.env.example` matches matrix (no secret values)  
- [x] Liveness vs readiness distinguished (`/health/live` · `/health/ready`)  
- [x] Readiness fails when DB or Redis unavailable (HTTP 503)  
- [x] Release smoke gate script runs curated suite after migrate  
- [x] Operator runbook: Compose → migrate → API → Worker → gate  
- [x] Worker (and key API paths) logs include `run_id` where applicable  
- [x] No new queue/scheduler/lifecycle; M1–M6 + E3 P0 contracts unchanged  
- [x] No APM/SIEM/CMS/IAM introduced  

---

## 6. Implementation steps (gated)

| Step | Deliverable | Gate |
|------|-------------|------|
| **DH.0** | This checklist confirmed | Human “go” for coding |
| **DH.1** | Config matrix + `.env.example` | After DH.0 |
| **DH.2** | Health live/ready (+ DB) | After DH.0 |
| **DH.3** | Release smoke / migration gate | After DH.0 |
| **DH.4** | Operator runbook (+ optional image pin notes) | After DH.0 |
| **DH.5** | Structured log keys Trace-aligned | After DH.0 |
| **DH.6** | Acceptance + freeze | — |

### Open points — **frozen for implementation**

1. Worker: **document-only** (no Worker HTTP)  
2. Dockerfile: **out of first slice**  
3. CI: **script + docs** (no GitHub Actions in DH v1)  
4. M3 smoke: **optional when `POSTGRES_RO_DSN` set**

---

## 7. Decision gate

| Decision | Meaning |
|----------|---------|
| **Approve checklist (design)** | Boundaries locked; still **no code** |
| **Authorize coding** | Separate explicit message after open points chosen |
| **Stay frozen** | Operate with current `/health` + manual smokes only |

**Current:** design checklist only. Await confirmation + open-point choices before coding.

---

## 8. Related

- [ERA_3_NEXT_VALUE_RANKING.md](./ERA_3_NEXT_VALUE_RANKING.md)  
- [PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md](./PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md)  
- [ERA_3_PLATFORM_MATURITY_REVIEW.md](./ERA_3_PLATFORM_MATURITY_REVIEW.md)  
- [STABLE_PHASE.md](./STABLE_PHASE.md)  

## 9. One-line summary

> **Deployment Hygiene** = config clarity + honest live/ready + migrate/smoke gate + Trace-aligned logs — so the Enterprise Data Agent Platform is **deliverable and operable**, without becoming an observability or job-platform product.
