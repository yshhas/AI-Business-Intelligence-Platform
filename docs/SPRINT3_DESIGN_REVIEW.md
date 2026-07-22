# Sprint 3 Design Review

**Status:** Design only · **awaiting approval** · no coding / commit / push / release  
**Base:** `e937f0a` (`main` ≡ `origin/main`)  
**Plan source:** `docs/V2_IMPLEMENTATION_PLAN.md` Sprint 3  

**Spine (immutable):**  
`Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts`

---

## 0. Executive summary

Sprint 3 makes **already-shipped backend capabilities visible** in the Product Shell, closes a known **output-redaction gap** on `table_preview`, and produces an **HITL design ADR** without implementing any approval state machine.

| Track | ID | Nature |
|-------|-----|--------|
| A | **P1.10** | Frontend UX — consume existing APIs |
| B | **P1.7** | Facade output hardening — `agent/guardrails.py` |
| C | **HITL** | Docs only — `awaiting_approval` design; **no Worker/lifecycle code** |

**Suggested coding order (when authorized):** P1.7 (small, backend) ∥ P1.10 (frontend) → HITL ADR last (docs).  
**Parallelism:** A and B are orthogonal; C has no code dependency.

---

## 1. Goals & boundary confirmation

### 1.1 Goals

| Goal | Success signal |
|------|----------------|
| Dual-Skill operable in UI | Analyze can submit `skill_id=data.bi` **or** `data.profile` |
| RO binding visible | Datasets page: postgres-ro usable; mysql-ro entry or explicit disabled |
| ACL operable | Owner can GET/PUT dataset ACL (users + can_read/can_run + optional tables) |
| Analyze progress coherent | Prefer SSE path; document/fix poll fallback consistency (already partial) |
| Preview redaction | `table_preview` cells/columns pass same heuristic redaction as summary/report |
| HITL readiness | ADR defines states/API/UX; marked **Non-goal for v1.1 implementation** |

### 1.2 Boundaries (in)

- Frontend pages/components/api clients that call **existing** Shell HTTP APIs.
- `agent/guardrails.py` (+ Facade call site already present) for preview coverage.
- Smoke / lint / build / optional demo checklist docs.
- HITL **design document** under `docs/`.

### 1.3 Boundaries (out) — see also §6 Non-goals

- No new Run statuses (`awaiting_approval` **not** coded).
- No Worker / `run_lifecycle` / cancel-path changes for HITL.
- No Policy Gate replacement; guardrails ≠ SQL authorization.
- No Semantic Layer, Multi-Agent, Celery/K8s, P1.4, P1.8 Cookie MVP.
- No v1.1 freeze/release in this Sprint.

### 1.4 Current gap (as-is)

| Capability | Backend | Frontend today |
|------------|---------|----------------|
| `skill_id` on create task | Supported | **Missing** — `createTask` body has no `skill_id` |
| postgres-ro bind | `POST .../datasets/postgres-ro` | **Present** on DatasetsPage |
| mysql-ro bind | `POST .../datasets/mysql-ro` | **Missing** client + UI |
| Dataset ACL GET/PUT | Routes exist | **Missing** client + UI |
| OIDC login UI | `/auth/oidc/*` | **Optional / thin** — may follow if IdP configured; not blocking MVP |
| Guardrails | Applied to summary/report/limitations | **`table_preview` not redacted** |
| Analyze SSE | `taskEvents` + poll fallback | Present; polish for skill display / filters only |

---

## 2. Module change list (proposed)

### 2.1 P1.10 — Frontend Product Shell Visibility

| Module | Change |
|--------|--------|
| `frontend/src/api/tasks.ts` | `createTask` accept optional `skill_id` |
| `frontend/src/pages/AnalyzePage.tsx` | Skill picker (`data.bi` / `data.profile`); show skill on running/result; default `data.bi` |
| `frontend/src/api/datasets.ts` | `bindMysqlRoDataset`; `getDatasetAcl` / `putDatasetAcl` |
| `frontend/src/types/dataset.ts` | ACL types if needed |
| `frontend/src/pages/DatasetsPage.tsx` | mysql-ro form (or disabled stub); ACL panel for owners when dataset selected |
| Optional | `LoginPage` OIDC button behind “OIDC available” probe — **stretch**, not required for Sprint 3 exit |
| Docs | Patch plan note in `docs/demo.md` (manual UX checklist) — implementation phase |

**Not required:** new backend routes for Skill/RO/ACL (already exist).

### 2.2 P1.7 — `table_preview` Guardrails

| Module | Change |
|--------|--------|
| `agent/guardrails.py` | Recursively redact string cells (and column names if string) under `table_preview` / chart-adjacent preview payloads as defined in PLATFORM_CONTRACTS |
| `agent/runtime.py` | No API change — already calls `apply_output_guardrails` |
| Smoke | Extend existing guardrails / data.profile / wave3 smoke with email/token in a preview cell |

**Placement rule:** Guardrails remain **post-Facade output** on `result_json` — not Policy, not Data Plane.

### 2.3 HITL Design-only

| Module | Change |
|--------|--------|
| `docs/HITL_SQL_APPROVAL_DESIGN.md` (new) | States, sequence, API sketch, UX, Non-goals, relation to P1.1 cancel/timeout |
| Optionally | Cross-link from `V2_IMPLEMENTATION_PLAN.md` / Roadmap — docs only |

**Zero** Python/TS lifecycle changes.

---

## 3. API / Contract impact

| Surface | Impact |
|---------|--------|
| Task create body | FE starts sending optional `skill_id` already accepted by backend — **additive client use**, no OpenAPI break |
| Dataset postgres-ro / mysql-ro | Unchanged contracts; FE adds mysql client |
| Dataset ACL GET/PUT | Unchanged contracts; FE consumes |
| Preview HTTP (`/datasets/.../preview`) | **Out of P1.7 scope unless separately decided** — P1.7 targets **Run `result_json.table_preview`**, not necessarily dataset preview endpoint |
| Auth / refresh | Unchanged (Sprint 2) |
| Run status enum | **Unchanged** — HITL does not add `awaiting_approval` in code |
| Kernel / Skill / Policy contracts | **Unchanged** |
| Trace schema | `platform.guardrails.applied` already set; may note preview coverage in docs |

**Clarifying decision for approval:**  
P1.7 default = redact **`result_json` table_preview** (Facade). Dataset `/preview` redaction is **optional follow-up** (same helpers) if product wants UI preview parity — recommend **include light reuse** on dataset preview service if cheap; otherwise defer to avoid expanding Shell surface mid-Sprint.

**Design recommendation:** Implement redaction helper once; apply in (1) Facade guardrails for Run results (**must**); (2) dataset preview path (**should**, same Sprint if &lt;0.5 day).

---

## 4. Spine impact analysis

| Layer | P1.10 | P1.7 | HITL design |
|-------|:-----:|:----:|:-----------:|
| Product Shell | ● UI + API clients | ○ / ◐ preview if shared | ○ docs |
| Worker | ○ | ○ | ○ **forbidden** |
| Kernel | ○ | ○ | ○ |
| Skill | ○ (invoked via existing skill_id) | ○ | ○ |
| Policy | ○ | ○ (not Gate) | ○ |
| Data Plane | ○ (bind UI only) | ○ | ○ |
| Trace / Artifacts | ◐ display skill | ◐ redacted preview fields | ○ future |

**How spine stays intact:**

1. UI only calls Product Shell HTTP — **never** imports Agent/Kernel.  
2. Guardrails stay on Facade output — **do not** move into Policy Gate.  
3. HITL ADR must state: approval pause would be a **future** Shell↔Worker status extension — **not** implemented in Sprint 3.

---

## 5. Release Gate / Eval impact

| Check | Expected Sprint 3 effect |
|-------|---------------------------|
| `smoke_release_gate` | Remain green; add/extend guardrails assertion |
| Eval core/quality/profile | **Should stay PASS** — redaction must not alter SQL/linking semantics; only display strings/cells |
| Frontend `lint` / `build` | **Required** for P1.10 |
| New smoke | Small guardrails preview case; ACL UI may stay manual checklist |
| Migration | **None expected** (no new tables/statuses) |
| Auth / cancel / memory Gate | Regression only — no intentional change |

**Risk to Eval:** Low if redaction is string-only and does not mutate numeric/boolean cells incorrectly (skip non-strings).

---

## 6. Non-goals (explicit)

1. **HITL implementation** — no `awaiting_approval`, no approve/reject API, no Worker pause.  
2. **P1.4** `result_json` cold/hot truncate.  
3. **P1.8** Cookie / HttpOnly token storage.  
4. **Semantic Layer / Multi-Agent / Agentic BI.**  
5. **IaC / Kubernetes / cloud deploy.**  
6. **Changing Spine or Policy Gate semantics.**  
7. **Device session UI / logout-all** (Sprint 2 follow-ups).  
8. **v1.1 release / tag / freeze.**  
9. Frontend redesign of entire workbench — **visibility patches only**, preserve existing UI language.  
10. Budget / FinOps UI (out of Sprint 3 plan).

---

## 7. Acceptance criteria (for later Implementation Review)

### P1.10

- [ ] Analyze Skill picker: `data.bi` / `data.profile`; create sends `skill_id`.  
- [ ] Trace/result shows which skill ran.  
- [ ] Datasets: postgres-ro remains; mysql-ro bind **or** clear disabled reason.  
- [ ] Owner ACL panel: list + replace grants (read/run; tables if API supports).  
- [ ] `npm run lint` && `npm run build` PASS.  

### P1.7

- [ ] Synthetic email/token in `table_preview` cell → redacted in Facade output.  
- [ ] `platform.guardrails.applied === true` still set.  
- [ ] Smoke covers preview redaction.  
- [ ] Eval suites PASS.  

### HITL Design-only

- [ ] ADR exists with: proposed states, sequence diagram, API sketch, UX wire notes, **Non-goal for v1.1 code**, interaction with cancel/timeout.  
- [ ] Explicit “implementation blocked until Phase 2 / separate auth”.  

---

## 8. Open decisions (need your sign-off before coding)

1. **Dataset `/preview` redaction:** include in P1.7 this Sprint (**recommended**) or Run `result_json` only?  
2. **mysql-ro UI:** full bind form (mirror postgres-ro) vs disabled placeholder until DSN configured?  
3. **OIDC login button:** in Sprint 3 MVP or defer? (**Recommend defer** unless IdP is in local demo.)  
4. **ACL tables_json editing:** expose in UI this Sprint or read/run flags only first?  
5. **HITL ADR filename:** `docs/HITL_SQL_APPROVAL_DESIGN.md` OK?

---

## 9. Risk rating

| Track | Risk | Notes |
|-------|------|-------|
| P1.10 | Low–Medium | UX scope creep; mitigate with checklist above |
| P1.7 | Low | Over-redaction of demo emails — acceptable / document |
| HITL docs | Low | Risk is accidental coding — process gate |
| Spine | Low | No Worker/Kernel changes planned |
| Gate/Eval | Low | String-only redaction |

**Design completeness:** Sufficient to authorize coding after decisions §8.

---

## 10. Pause

**No code · no commit · no push · no v1.1 release · no Sprint 3 implementation until Design Review approved.**

Please confirm §8 decisions (or amendments), then authorize Sprint 3 coding.
