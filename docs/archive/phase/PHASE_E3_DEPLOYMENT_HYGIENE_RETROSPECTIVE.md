# Phase E3 — Deployment Hygiene Freeze + Retrospective

**Status:** ✅ **Formally closed / frozen** (2026-07-22)  
**Slice:** Era 3 Deployment Hygiene (DH.1–DH.5)

## Narrative completed

```text
E3 P0:  Runtime has capacity + crash honesty
E3 DH:  Platform can be deployed, verified, and operated repeatably
```

**Proof (not an observability product):**
> Enterprise Data Agent Platform 从「架构上可 Demo」进一步到「配置清晰 · 探针诚实 · 门禁可重复 · 日志可与 Trace 对齐」——不引入 APM/SIEM/新服务面。

## Freeze (do not expand now)

| Keep | Do not |
|------|--------|
| Config matrix + `.env.example` | Secrets manager / remote config product |
| `/health/live` · `/health/ready` (DB+Redis) | Worker HTTP health endpoint |
| `smoke_release_gate.py` (+ conditional M3) | Mandatory browser e2e / LLM-full CI |
| `OPS_RUNBOOK.md` (Compose + venv) | Dockerfile for API/Worker (this freeze) |
| Trace-aligned `run_id` / `failure_class` logs | APM / SIEM / OpenTelemetry stack |
| Script + docs gate | GitHub Actions as must-have |

**Still frozen elsewhere:** workspace concurrency · `replay_of` · auto-retry/resume · Celery/Kafka/Streams · scheduler/FinOps · hard-kill · IAM · Connector Framework · Marketplace · Multi-Agent · Report Center/CMS · E3 P0 Runtime reopen

M1–M6 contracts unchanged. Kernel / Skill / Policy / Trace / Artifact models untouched.

---

## Retrospective

### 1. What changed for operators

| Before DH | After DH |
|-----------|----------|
| Ad-hoc env knowledge | [OPS_CONFIG_MATRIX.md](../../ops/OPS_CONFIG_MATRIX.md) |
| Single `/health` mix | Explicit **live** vs **ready** |
| Manual smoke scatter | One **release gate** script |
| Worker “is it up?” unclear | Documented process checks (no new HTTP) |
| Logs hard to join to Trace | Structured keys aligned with Run Trace |

### 2. Design choices that held

| Choice | Why |
|--------|-----|
| Ready = DB + Redis only | Matches enqueue / Worker dependency without over-probing |
| Worker docs-only | Avoids second service surface; Analyze still proves Worker |
| M3 conditional | Core/file path gate stays green without RO plane |
| Logs correlate, Trace remains truth | Protects M4 model from log-product drift |
| No Dockerfile / Actions in v1 | Stabilize current Compose+venv path first |

### 3. Remaining gaps (accepted)

| Gap | Note |
|-----|------|
| API/Worker not containerized | Stretch later if deploy target requires |
| No CI orchestration | Script is the gate; Actions optional later |
| Worker not in readiness probe | Intentional; document + Run progress |
| No alembic-revision-in-ready | Optional crumb; migrate is gate step |

Do **not** fill these by opening APM or Runtime complexity next.

### 4. Era 3 posture after this freeze

```text
Era 3 so far:
  ✅ Runtime Essentials P0
  ✅ Deployment Hygiene
```

Platform credibility now covers **execution boundaries** and **deliver/operate hygiene**.  
Next slice should be **value-ranked again** (design only) — candidates remain Skill Lifecycle lite / evidence-gated Runtime deferred / second-Skill charter — **not** more probes or job-platform work.

---

## Related

- [PHASE_E3_DEPLOYMENT_HYGIENE_ACCEPTANCE.md](PHASE_E3_DEPLOYMENT_HYGIENE_ACCEPTANCE.md)  
- [PHASE_E3_DEPLOYMENT_HYGIENE_CHECKLIST.md](PHASE_E3_DEPLOYMENT_HYGIENE_CHECKLIST.md)  
- [OPS_RUNBOOK.md](../../ops/OPS_RUNBOOK.md) · [OPS_CONFIG_MATRIX.md](../../ops/OPS_CONFIG_MATRIX.md)  
- Prior: [PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md](PHASE_E3_RUNTIME_ESSENTIALS_RETROSPECTIVE.md)  
- Ranking context: [ERA_3_NEXT_VALUE_RANKING.md](../era/ERA_3_NEXT_VALUE_RANKING.md) (pre-DH; refresh after this freeze before coding next)
