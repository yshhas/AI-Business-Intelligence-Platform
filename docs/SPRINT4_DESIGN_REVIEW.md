# Sprint 4 Design Review

**Status:** Design only · **awaiting approval** · no coding / commit / push / release  
**Base:** `d242bf4` (`main` ≡ `origin/main` after Sprint 3 push)  
**Plan source:** `docs/V2_IMPLEMENTATION_PLAN.md` Sprint 4  

**Spine (immutable):**  
`Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts`

---

## 0. Context after push

| Item | State |
|------|-------|
| Sprint 3 on remote | `d242bf4` pushed · ahead/behind **0/0** |
| Untracked local | `docs/SPRINT3_FINAL_AUDIT.md` (archive when authorized) |
| Sprint 4 coding | **Not authorized** |
| v1.1 release/tag | **Not authorized** |

---

## 1. Goals & boundary

### 1.1 Goals

| Track | Goal |
|-------|------|
| **P1.4** | Bound hot `result_json` size; keep Trace/Artifact usable; **backward-compatible** reads |
| **P1.8** | Ship **Token Storage ADR** (localStorage + short access TTL + refresh revoke). Cookie **not** default-landed |
| **v1.1 docs** | Plan CHANGELOG / RELEASE_NOTES / exit checklist content — **design/draft only**, no tag |

### 1.2 Out of Sprint 4 coding (Non-goals)

- Phase 2: Semantic Layer, HITL **implementation**, Multi-Agent, Agentic BI  
- Phase 3: Terraform / K8s / cloud IaC  
- Cookie HttpOnly MVP (unless separately approved later — **default = ADR only**)  
- Celery, RAG, Catalog, P1.9 mega-refactor  
- Changing Spine direction or Policy Gate semantics  

---

## 2. Current as-is (relevant to P1.4 / P1.8)

### 2.1 `result_json` & Artifacts today

- Worker persists full Facade `result_json` on `analysis_tasks.result_json` (JSONB).  
- M6 `artifact_service.materialize_for_task` writes `run_artifacts` with **`content_ref` into `result_json` fields** (does not duplicate blobs to object store).  
- Trace (`GET .../execution`) reads `platform` from `result_json`.  
- `TaskOut.result_json` returned on task GET/list items (list may carry large payloads).  
- FE Analyze uses both `task.result_json` and Artifacts API.

**Pain:** Large `table_preview` / `report.markdown` / charts inflate Postgres row size, backups, and list responses.

### 2.2 Token storage today

- Access + refresh in **localStorage** (`authStore`).  
- Refresh **jti revoke** landed (Sprint 2).  
- Access TTL short (~30m); refresh ~7d.  
- No HttpOnly Cookie path.

---

## 3. P1.4 — `result_json` hot / cold / truncate

### 3.1 Recommended strategy (MVP for v1.1)

**Prefer “hot slim + artifact refs” over new object store** (keeps ops simple; Artifacts already exist).

| Layer | Proposal |
|-------|----------|
| **Hot `result_json`** | Always keep: `summary` (bounded), `sql`, `platform` (run/execution/authz/sql_quality), small `limitations`, `charts` **metadata** or capped count |
| **Heavy fields** | Cap or strip from hot row: `table_preview.rows` beyond N, oversized `report.markdown`, excess chart series |
| **Cold / full** | Prefer **Artifacts** (`content_ref`) + optional `platform.result_payload` flags; if stripped, FE loads via artifact GET |
| **Config** | e.g. `RESULT_JSON_MAX_BYTES`, `TABLE_PREVIEW_MAX_ROWS` (defaults TBD in impl) |

**Algorithm (Worker persist, after Facade + guardrails):**

1. Materialize artifacts (existing).  
2. Apply size policy: if over budget, truncate `table_preview.rows` / markdown with marker in `limitations` + `platform.payload` (`truncated: true`, `schema_version`).  
3. Persist slim hot JSON.  
4. Do **not** delete artifact rows that still point at remaining fields; if a field is fully moved, update `content_ref` semantics carefully (see compatibility).

### 3.2 Backward compatibility (required)

| Consumer | Compatibility rule |
|----------|-------------------|
| Old FE / API clients | Must still parse `TaskOut`; missing heavy fields → empty table/report with caption, not 500 |
| `platform.execution` Trace | **Must remain** on hot JSON (or equivalent projection) — UI Trace must not break |
| Artifacts list/detail | Remain source of truth for typed payloads when hot field truncated |
| `failure_class` / status | Unchanged |
| OpenAPI | Additive `platform.payload` optional; no required new fields for old clients |

**Versioning:** `platform.payload.schema_version: 1` when truncation applied; omit when untouched (legacy shape).

### 3.3 Trace / Artifact contract impact

| Contract | Change |
|----------|--------|
| Trace | Keep `platform.execution` + tool/policy summaries in hot path; do not require full `table_preview` for Trace honesty |
| Artifact refs | Continue `content_ref` into result fields; if truncated, ref may note `partial` or point to remaining slice |
| Kernel/Skill | **No contract change** — truncation is **Worker persist policy** after Facade |
| Policy / Data Plane | **No change** |

### 3.4 Modules (when coding authorized)

| Module | Role |
|--------|------|
| `analysis_worker` success/fail persist | Apply slim policy before commit |
| New helper e.g. `result_payload.py` | Truncate/measure bytes |
| `artifact_service` | Minor: tolerate truncated fields; no new store required for MVP |
| `config.py` / `.env.example` / OPS | Caps |
| FE `TaskResultPanel` | Graceful empty/truncated banner |
| Smokes | Large synthetic preview → hot size ≤ cap; Trace still loads |

### 3.5 Alternatives considered (not default)

| Option | Why not default |
|--------|-----------------|
| Full S3/MinIO cold store | Ops/IaC creep (Phase 3 adjacent) |
| Drop `result_json` entirely | Breaks Trace/list consumers |
| Truncate only in API response | DB still bloated — misses root issue |

---

## 4. P1.8 — Token storage ADR (**ADR-only default**)

### 4.1 Decision for Sprint 4 (proposed)

**Ship ADR document only:** accept **localStorage** for access + refresh for v1.1, with compensating controls already/partially in place:

| Control | Status |
|---------|--------|
| Short access TTL | Exists (~30m) |
| Refresh revoke / rotation | Exists (P1.2) |
| Logout revokes current refresh | Exists |
| XSS → token theft residual risk | **Accepted** for v1.1 with documented mitigations (CSP later, no Cookie CSRF surface) |

**Cookie / HttpOnly:** documented as **future option** (requires CSRF, SameSite, CORS, FE rewrite) — **not implemented in Sprint 4** unless you override this Design.

### 4.2 ADR deliverable

Suggested path: `docs/ADR_TOKEN_STORAGE.md`

Must include: context, decision, consequences, alternatives (Cookie), relation to P1.2, explicit Non-goal “Cookie MVP not in v1.1”.

### 4.3 API / Gate impact (ADR-only)

| Surface | Impact |
|---------|--------|
| Auth API | None |
| FE | None (docs may note current localStorage) |
| Release Gate | No new smoke required for ADR-only |
| Spine | None |

---

## 5. v1.1 Release documentation planning (design only)

### 5.1 Planned artifacts (write in Sprint 4 impl / exit — not tag now)

| Doc | Purpose |
|-----|---------|
| `CHANGELOG.md` | [1.1.0] section: Sprints 1–4 user-facing notes |
| `RELEASE_NOTES.md` | Pilot-facing summary; upgrade (migrate `0014`, re-login after refresh_sessions) |
| Optional `docs/V1_1_EXIT_AUDIT.md` | Exit criteria checklist sign-off |
| Update `README` links | Point to v1.1 when tagged later |

### 5.2 Exit criteria mapping (from plan)

| # | Criterion | Sprint 4 action |
|---|-----------|-----------------|
| ① Gate + Eval | Re-run at exit; must green |
| ② cancel/revoke coverage | Already green — regression |
| ③ UI Skill/ACL/RO | Done Sprint 3 |
| ④ Memory + **result_json** bounds | Memory done; **P1.4 closes gap** |
| ⑤ ANALYSIS_RUNTIME | Done Sprint 1 |
| ⑥ CHANGELOG / RELEASE_NOTES / audit | **This track** |
| ⑦ No Won't-Do | Process gate |

### 5.3 Explicit: no release in Design phase

Design may draft text; **tag `v1.1.0` / GitHub Release only after separate authorization** post-coding + exit audit.

---

## 6. Spine impact

| Track | Shell | Worker | Kernel | Skill | Policy | Plane | Trace |
|-------|:-----:|:------:|:------:|:-----:|:------:|:-----:|:-----:|
| P1.4 | ◐ FE fallback | ● persist slim | ○ | ○ | ○ | ○ | ◐ projection kept |
| P1.8 ADR | ○ docs | ○ | ○ | ○ | ○ | ○ | ○ |
| v1.1 docs | ○ docs | ○ | ○ | ○ | ○ | ○ | ○ |

Worker still only via Facade; Gate unchanged; Artifacts remain Shell metadata over result refs.

---

## 7. Release Gate / Eval impact

| Item | P1.4 | P1.8 ADR | Docs |
|------|------|----------|------|
| `smoke_release_gate` | Update/add payload-size or truncated-preview smoke | No | No |
| Eval c/q/p | Must stay PASS (truncation must not alter SQL/linking) | No | No |
| FE lint/build | If FE banner added | No | No |
| Migration | Prefer **config-only** MVP; avoid new tables unless cold store chosen | No | No |

---

## 8. Non-goals (restate)

1. No Cookie implementation by default.  
2. No HITL / Semantic / Multi-Agent / IaC.  
3. No Kernel/Policy/Data Plane semantic rewrite.  
4. No v1.1 tag during Design.  
5. No object-store platform unless explicitly escalated.  

---

## 9. Open decisions (need sign-off before coding)

1. **P1.4 MVP:** approve “hot slim + truncate heavy fields + Artifacts remain” (recommended) vs introduce file/object cold store?  
2. **List tasks:** strip `result_json` from list responses (API behavior change) or keep slim-only in DB so list is naturally small? (**Recommend:** slim in DB; optional also omit `result_json` on list later as additive query flag — not required for MVP.)  
3. **P1.8:** confirm **ADR-only** (no Cookie code) for Sprint 4.  
4. **Caps defaults:** e.g. preview max rows **50→keep display cap 20 in hot**, max hot JSON **256 KiB** — accept as starting point?  
5. **SPRINT3_FINAL_AUDIT.md:** include in next docs commit with Sprint 4 or separate docs commit now?

---

## 10. Suggested coding order (when authorized)

```text
1) P1.8 ADR doc (fast)
2) P1.4 helper + Worker persist + smoke + FE truncated UX
3) CHANGELOG / RELEASE_NOTES drafts
4) Full Gate + Eval → Implementation Report → Review → commit
5) (Later auth) push → v1.1 exit audit → tag
```

---

## 11. Risk rating

| Track | Risk |
|-------|------|
| P1.4 | **Medium** — compatibility / FE empty states |
| P1.8 ADR | **Low** |
| Docs | **Low** |
| Spine | **Low** if truncation stays post-Facade Worker-side |

---

## 12. Pause

**No Sprint 4 coding · no commit · no release.**  

Please confirm §9 decisions, then authorize Sprint 4 implementation (and separately whether to archive `SPRINT3_FINAL_AUDIT.md`).
