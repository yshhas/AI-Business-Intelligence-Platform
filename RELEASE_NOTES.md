# Release Notes — v1.1.0 (draft)

**Status:** Draft for Sprint 4 exit · **tag not cut**  
**Base:** Phase 1 Sprints 1–4 on `main`  
**Spine:** Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts

> v1.0 froze the governed spine. **v1.1** adds honest runtime cancel, refresh revoke, bounded memory/results, Product Shell visibility, and documented token storage — without Phase 2 features.

Canonical plan: [docs/V2_IMPLEMENTATION_PLAN.md](docs/archive/roadmap/V2_IMPLEMENTATION_PLAN.md) · Token ADR: [docs/ADR_TOKEN_STORAGE.md](docs/design/ADR_TOKEN_STORAGE.md)

---

## Summary

Pilot-ready hardening on top of v1.0:

- Cooperative cancel/timeout + write fence  
- Refresh session revoke / rotation / logout  
- Memory TTL/cap · hot `result_json` bounds  
- Skill picker · ACL UI · preview guardrails  
- HITL design-only · Token storage ADR (localStorage accepted)

---

## Upgrade notes

1. `alembic upgrade head` (includes `0014_sprint2_refresh_memory`)  
2. Re-login after deploy (old refresh tokens without `jti` rows fail refresh)  
3. Optional env: `RESULT_JSON_MAX_BYTES=262144`, `TABLE_PREVIEW_HOT_MAX_ROWS=50`  
4. Optional: `WORKSPACE_MEMORY_TTL_DAYS`, `WORKSPACE_MEMORY_MAX_ROWS`

---

## Non-goals in 1.1.0

- Cookie/HttpOnly auth MVP  
- HITL SQL approval **code**  
- Semantic Layer / Multi-Agent / Terraform / K8s  

---

# Release Notes — v1.0.0

**Release Title:** Enterprise Data Agent Platform v1.0 — Feature Freeze  
**Date:** 2026-07-22  
**Status:** Stabilization complete · Waves 0–3 done · Wave 4 not started

> A governed Enterprise Data Agent Platform — not a ChatBI toy or a free-form ReAct demo.

Canonical deep dive: [docs/FINAL_RELEASE.md](docs/FINAL_RELEASE.md) · Marker: [RELEASE.md](RELEASE.md)

---

## Summary

v1.0 freezes a demo-ready, interview-ready platform spine:

```text
Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts
```

The first Skill (`data.bi`) delivers Text-to-SQL → table / chart / report.  
The second Skill (`data.profile`) proves the platform can extend under the same contracts.

---

## Highlights

### Core features

- Governed **Run** lifecycle (enqueue · claim · timeout · cancel · capacity · budget)
- Kernel Skill / Tool / Policy / Artifact registry with lifecycle enable/version
- Triple SQL SELECT gate (Skill · Tool · Plane) + Dataset ACL allowlist projection
- Data planes: `file` (DuckDB) · `postgres_ro` · optional `mysql_ro`
- Trace / Artifacts / `failure_class` as execution truth; SSE task progress (not token streaming)
- Auth: JWT access + refresh · optional OIDC · Redis rate limits · output guardrails
- Eval golden suites + Release gate (`smoke_release_gate`) + CI

### Tech stack

| Layer | Stack |
|-------|--------|
| Frontend | React · TypeScript · Vite · TanStack Query |
| API | FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · PyJWT · Redis |
| Agent | LangGraph (`data.bi` fixed graph) · sqlparse Gate · httpx LLM |
| Data | DuckDB · Postgres · optional PyMySQL |
| Quality / CI | PyYAML eval suites · GitHub Actions · smoke scripts |
| Observability | prometheus_client · request_id · run_id / failure_class logs |

### Architecture highlights

1. One spine for all capabilities — avoids “Agent toy” divergence  
2. Defense-in-depth SQL policy (gated up to 3× per query)  
3. Second Skill proves extensibility without special-casing  
4. Honest failure taxonomy via `failure_class` + Trace  
5. Falsifiable quality: Eval baselines enter the Release Gate  
6. Least privilege: Dataset ACL projects into Gate allowlist  

---

## Known Issues

| Severity | Issue |
|----------|--------|
| P1 | Worker timeout may leave orphan step writers (needs cooperative cancel) |
| P1 | `list_tasks` N+1 Dataset loads (perf polish) |
| P1 | JWT refresh not revoked (`jti` unused) |
| P2 | `ANALYSIS_RUNTIME` default remains `mock` (set `agent` for demos) |
| P2 | Unbounded workspace memory growth (TTL / cap later) |
| P2 | Large `result_json` retained in Postgres (archive later) |
| P2 | OIDC / MySQL RO not production-validated against a real IdP |

See also: [docs/FINAL_STABILIZATION_REVIEW.md](docs/archive/reviews/FINAL_STABILIZATION_REVIEW.md) §4–§6.

---

## Future Roadmap (not in v1.0)

| Priority | Item |
|----------|------|
| A | Wave 4 — single-cloud IaC (AWS **or** Tencent Cloud) + secrets |
| B | Refresh token revoke / rotation store |
| C | Real IdP + MySQL staging soak |
| D | Cooperative Run cancel on timeout |
| E | `result_json` hot/cold truncate |
| F | Memory row TTL / per-workspace cap |
| G | Frontend skill picker for `data.profile` |
| H | Celery / incremental steps — **only with metrics evidence** |

**Explicit non-goals (frozen):** RAG as main path · free-form ReAct · LangChain rewrite of main path · WebSocket chat · Connector Framework · Code Agent · multi-cloud IaC at once.

---

## Upgrade / Install

```powershell
copy .env.example .env
# Demo: set ANALYSIS_RUNTIME=agent and a strong JWT_SECRET
docker compose -f docker/docker-compose.yml --env-file .env up -d --build
```

Release quality bar:

```powershell
cd backend
python scripts/smoke_release_gate.py
cd ../frontend
npm run lint
npm run build
```

---

## App version

- App version string: `1.0.0`
- Git tag (after push): `v1.0.0`
