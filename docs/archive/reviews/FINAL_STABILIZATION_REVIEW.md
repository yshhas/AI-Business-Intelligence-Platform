# Final Stabilization Review Report

**Date:** 2026-07-22  
**Scope:** Post–Wave 3 polish for enterprise demo / deploy narrative  
**Constraint:** No Wave 4 · no new product features · stability/docs/quality only

---

## 1. 当前项目完成度

| Area | Score | Notes |
|------|-------|-------|
| Platform spine (Shell→Worker→Kernel→Skill→Policy→Plane→Trace) | **~95%** | Intact; second Skill proves extensibility |
| Trust (Auth / Rate / Config harden / Eval) | **~90%** | JWT refresh without revocation; OIDC MVP hardened in Stabilization |
| Operate (Metrics / Compose / Linking / Repair) | **~90%** | Prometheus + Worker health; Grafana optional profile |
| Platform proof (Wave 3) | **~85%** | MVP surfaces exist; real IdP/MySQL not production-validated |
| Enterprise deploy (Wave 4) | **0%** | Explicitly not started |
| **Overall demo-ready** | **~88%** | Suitable for architecture demo / interview / pilot staging with documented limits |

---

## 2. 已实现能力

### Core platform

- Kernel registry + `kernel.run(RunRequest)` with lifecycle enable/version
- Skills: **`data.bi`** (LangGraph Text-to-SQL) · **`data.profile`** (deterministic profile)
- Policy: `sql.select_gate` + plane re-gate
- Planes: `file` / `postgres_ro` / optional `mysql_ro`
- Trace / Artifacts / `failure_class` / SSE progress
- Dataset ACL + table projection into Gate allowlist
- Soft cost budget · capacity · rate limits · Idempotency-Key
- Workspace memory (linking synonyms)
- Optional OIDC (state + issuer-host SSRF guard)
- MCP HTTP read-only tools (ACL-bound)
- Output guardrails (summary/report redaction)
- Eval suites: core · quality · profile (+ optional llm)
- Release gate + Frontend lint/build CI job

---

## 3. Stabilization 本轮已修复（稳定性）

| Issue | Fix |
|-------|-----|
| OIDC SSRF via discovery endpoints | Host must match issuer |
| OIDC `state` unused | Redis store + consume on callback |
| Predictable OIDC local password | `secrets.token_urlsafe` |
| MCP allowlist caller-controlled | Require `dataset_id`; ACL projection |
| MySQL row shape ≠ DuckDB/Postgres | Return `list[dict]` |
| `data.profile` row parse | Support dict + tuple rows |
| Idempotency race / fail-open in prod | SET NX claim; fail-closed when hardened |
| Rate limit fail-open in prod | Fail-closed when hardened |
| Skill registry import fail → hardcoded allow | Fail closed |
| AnalyzePage hooks warning | Fresh `getTask` status; deps = `[task?.id, workspaceId]` |
| `failure_class` label drift | `enqueue_error` + missing classes |
| Docs lag Wave 3 | README / PHASES / API / OPS / `.env.example` / plan |

---

## 4. 仍存在的问题（未在本轮扩大范围修复）

| Severity | Issue | Why deferred |
|----------|-------|--------------|
| P1 | Worker timeout may leave orphan step writers | Needs cooperative cancel design |
| P1 | `list_tasks` N+1 Dataset loads | Perf polish; not demo-blocking |
| P1 | JWT refresh not revoked (`jti` unused) | Wave 4 / auth product |
| P2 | Gate applied up to 3× per query | Intentional defense-in-depth |
| P2 | `DataPlane` protocol unused (marker only) | Avoid premature abstraction |
| P2 | Guardrails skip `table_preview` / steps | Compliance product ≠ MVP |
| P2 | `ANALYSIS_RUNTIME` default still `mock` | Documented; set `agent` for demos |
| P2 | Connector code triplication | Extract only with evidence |
| P2 | Unbounded workspace memory growth | Cap/TTL later |
| P2 | Large `result_json` in Postgres | Archive strategy Wave 4+ |

---

## 5. 技术债清单

1. Shell↔Kernel coupling for skill catalog in `permissions.py`
2. Worker enrichment after Facade (authz snapshot / memory write)
3. Fake `member_role` smoke path weaker than real ACL
4. Pydantic `DatasetOut.schema_json` shadows BaseModel (warning only)
5. Frontend Analyze still manual fetch/SSE vs TanStack Query on list pages
6. Historical docs (`ERA_3_*`, old checklists) partially superseded by `project_upgrade_plan.md`

---

## 6. 建议后续迭代（**暂不实现**）

| Priority | Item | Wave |
|----------|------|------|
| A | Single-cloud IaC (AWS **or** 腾讯云) + secrets | Wave 4 |
| B | Refresh token revoke / rotation store | Wave 4 / Trust+ |
| C | Real IdP + MySQL staging soak test | Ops |
| D | Cooperative Run cancel on timeout | Runtime |
| E | `result_json` hot/cold truncate | Data |
| F | Memory row TTL / per-workspace cap | AI6+ |
| G | Frontend skill picker for `data.profile` | Shell UX |
| H | Celery / incremental steps | **Only with metrics evidence** |

---

## 7. 质量门禁期望

After Stabilization commits, operators should see:

- `python scripts/smoke_release_gate.py` → **PASS**
- `cd frontend && npm run lint && npm run build` → **PASS** (no hooks warning)

---

## 8. 结论

平台已达到 **「可治理 Data Agent 脊柱 + 可证明第二 Skill + 可演示运维门禁」** 的企业级展示水位。  
Wave 4 属于交付/部署深化，**不是**功能叙事补齐；在未授权前应保持 Stabilization 冻结，避免范围膨胀。
