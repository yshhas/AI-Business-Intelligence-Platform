# Phase M5 — Resource Permission (thin RBAC) Checklist（仅设计，待确认后编码）

**Status:** ✅ **Frozen** — see [PHASE_M5_ACCEPTANCE.md](PHASE_M5_ACCEPTANCE.md) / [PHASE_M5_RETROSPECTIVE.md](PHASE_M5_RETROSPECTIVE.md)  
**Era:** 2 — Enterprise Capability Enhancement  
**Prerequisite:** M4 Traceable Execution **frozen**  
**Theme:** Thin resource authorization — not IAM  
**Parent:** [ENTERPRISE_CAPABILITY_ROADMAP.md](../roadmap/ENTERPRISE_CAPABILITY_ROADMAP.md) · [ENTERPRISE_M4_M6_RANKING.md](../roadmap/ENTERPRISE_M4_M6_RANKING.md)

**Confirmed open points (2026-07-22)**
| # | Decision |
|---|----------|
| 1 Viewer Analyze | ❌ cannot create Run |
| 2 Viewer upload | ❌ cannot upload |
| 3 Run visibility | Workspace-wide for members (no private Run) |
| 4 Dataset ACL | Role matrix only (no per-dataset ACL) |
| 5 Errors | Cross-workspace 404; in-workspace role fail 403 |
| 6 Demo | Direct `role` change; no invite/UI |

**Goal**

```text
Agent Run
    ↓
Execution Trace          (M4 — frozen)
    ↓
Authorized Resource Access   (M5)
```

> 在 Workspace 角色之上，把 **Dataset / Data Plane / Run / Skill(预留)** 的访问规则说清楚、可执行、可 Demo——不做企业组织与身份套件。

**Hard stop-lines**

- No IAM product / SSO / Invite / org hierarchy / SCIM  
- No ABAC policy language / external PDP  
- No permission engine inside Kernel  
- No M6 Artifact CMS; no second Skill; no Connector Framework  
- Keep existing roles: `owner | analyst | viewer` (no new role proliferation unless unavoidable)

---

## 0. Architecture invariant

```text
Product Shell (API deps + permission helpers)
        |
    authorize(action, resource)
        |
Worker / task_service / dataset_service   ← enforce
        |
Kernel / Skill / Policy / Trace           ← unchanged (no authz inside)
```

Denied access → HTTP 403 (or 404 to hide existence where already used) + optional note in Demo; **do not** invent Audit events for every deny (M4 Trace stays execution-centric). Optional: surface deny reason string in API `detail` only.

---

## 1. As-is permission map (Foundation + companions)

| Action | Today | Gap |
|--------|-------|-----|
| Workspace enter | Member required | OK |
| List/get Dataset | Any member | Viewer can see all; no per-dataset ACL |
| Upload file Dataset | Any member | May be too open vs analyst-only |
| Bind `postgres_ro` | owner \| analyst | Companion only; not named as plane permission |
| Preview Dataset | Any member | OK for thin; optional tighten |
| Create Run (file) | Any member | Viewer can Analyze |
| Create Run (`postgres_ro`) | owner \| analyst | Companion; not unified matrix |
| Get Run / steps / **execution** | Any member | Viewer sees all Runs in workspace |
| Cancel Run | creator \| owner | Analyst cannot cancel own? Creator yes; OK |
| Rename workspace | owner \| analyst | Existing |

**Problem:** Rules are **scattered** and **incomplete** relative to enterprise story (especially Run visibility + plane access).

---

## 2. Target model (thin)

### 2.1 Roles (reuse — do not invent IAM)

| Role | Intent |
|------|--------|
| `owner` | Full workspace control |
| `analyst` | Bind planes, run Analyze, manage most data ops |
| `viewer` | Read-only: see allowed Datasets/Runs/Traces; **no** bind, **no** create Run, **no** upload (proposed) |

### 2.2 Resources

| Resource | Identity |
|----------|----------|
| **Workspace** | `workspace_id` (existing membership gate) |
| **Dataset** | `dataset_id` (+ `source_type`) |
| **Data Plane** | Logical capability on Dataset: `file` \| `postgres_ro` (not a separate Connector entity) |
| **Run** | `task_id` / Run |
| **Skill** | `skill_id` — **reserve only** in M5 (`data.bi` always allowed if Run allowed) |

### 2.3 Actions (M5 vocabulary)

| Action | Resource | Meaning |
|--------|----------|---------|
| `dataset.list` / `dataset.get` / `dataset.preview` | Dataset | Read metadata/preview |
| `dataset.create_file` | Workspace | Upload file dataset |
| `dataset.bind_postgres_ro` | Workspace / Plane | Bind RO source |
| `plane.use` | Dataset+plane | Use dataset as Analyze source |
| `run.create` | Dataset | Start analysis |
| `run.get` / `run.list` / `run.execution` / `run.steps` | Run | Visibility of Run + Trace |
| `run.cancel` | Run | Cancel |
| `skill.invoke` | Skill | **Reserved** — M5: always `data.bi` if `run.create` allowed |

---

## 3. Proposed authorization matrix (default)

| Action | owner | analyst | viewer |
|--------|-------|---------|--------|
| dataset.list/get/preview | ✅ | ✅ | ✅ |
| dataset.create_file | ✅ | ✅ | ❌ |
| dataset.bind_postgres_ro | ✅ | ✅ | ❌ |
| plane.use file | ✅ | ✅ | ❌ (no run) |
| plane.use postgres_ro | ✅ | ✅ | ❌ |
| run.create | ✅ | ✅ | ❌ |
| run.get/list/execution/steps | ✅ | ✅ | ✅\* |
| run.cancel | ✅ creator\|owner; analyst if creator | same | ❌ |
| skill.invoke data.bi | via run.create | via run.create | ❌ |

\* **Run visibility (open point):**  
- **A (recommended for Demo simplicity):** any workspace member can view all workspace Runs/Traces  
- **B (stricter):** viewer sees all; analyst/owner all; **or** viewer only Runs they… (viewers don't create — meaningless)  
- **C:** Runs visible only to creator + owner (breaks shared Demo)

**Recommendation:** **A** for M5 — visibility is workspace-scoped; restriction focus is **mutate/bind/run**, not hide Traces. M4 Trace value remains Demoable for all members.

### 3.1 Optional per-Dataset ACL (thin stretch)

**Default M5: role matrix only** (no `dataset_acl` table).

**Stretch if needed for narrative “resource-level”:**

| Approach | Pros | Cons |
|----------|------|------|
| Role matrix only | Simple; matches stop-lines | Weak “resource” story |
| `datasets.visibility` = `workspace` \| `restricted` + member allowlist JSON | True resource gate | Extra UX; invite-like smell |

**Recommendation:** Ship **role matrix first**. If Demo needs “Dataset X only for analysts”, add **one** field `access_level: workspace|analysts_only` on Dataset — still no IAM.

---

## 4. Data Plane / Connector access

| Rule | Design |
|------|--------|
| Bind `postgres_ro` | owner \| analyst only (codify as `dataset.bind_postgres_ro`) |
| Run against `postgres_ro` | owner \| analyst (`plane.use` + `run.create`) |
| Run against `file` | owner \| analyst (viewer cannot create Run) |
| Secrets | Still env DSN only; permission ≠ credential ACL product |
| Naming | Call it **Data Plane permission** in docs; API may keep `postgres-ro` path |

No Connector registry permissions object.

---

## 5. Run visibility & Trace

| API | Enforce |
|-----|---------|
| `GET /tasks` | Member + role matrix; filters unchanged |
| `GET /tasks/{id}` | Member (+ optional creator-only if choosing C — not recommended) |
| `GET /tasks/{id}/execution` | Same as get Run — Trace is not a separate ACL resource |
| `GET /tasks/{id}/steps` | Same |
| `POST /tasks` | `run.create` + `plane.use` for dataset.source_type |
| `POST .../cancel` | Keep creator \| owner (analyst-as-creator already covered) |

**Trace deny:** 403 with clear `detail` (e.g. “viewer cannot create runs”) — do not write fake PolicyDecision into execution for authz denies (different concern from SQL Policy).

---

## 6. Skill permission (reserved)

| M5 | Later |
|----|-------|
| Hardcode allow `data.bi` when `run.create` passes | Table/registry: `workspace_skill_grants` when second Skill exists |
| Document `skill.invoke` in matrix as reserved | Skill lifecycle phase |

Do **not** build skill grant UI in M5.

---

## 7. Implementation shape (when coding)

### 7.1 Central helper (Product Shell)

```text
backend/app/services/permissions.py  (name TBD)

can(member, action, *, dataset=None, task=None, skill_id=None) -> bool
require(...) -> raise TaskServiceError/HTTP 403
```

Replace scattered `_require_bind_role` / postgres run checks with matrix calls.

### 7.2 Enforcement points

| Module | Checks |
|--------|--------|
| `routes_datasets` | create_file, bind_postgres_ro, preview (if tightened) |
| `routes_tasks` / `task_service` | create, list/get/execution/steps, cancel |
| Worker | **No** re-auth beyond task already authorized at create (avoid Worker IAM) |

### 7.3 Schema

| Change | M5 default |
|--------|------------|
| New ACL tables | **No** |
| New roles | **No** |
| Dataset `access_level` | Optional stretch only |
| Audit authz denials table | **No** |

### 7.4 UI (minimal)

| In | Out |
|----|-----|
| Disable/hide Upload / Bind / Analyze for viewer | Full admin permission console |
| 403 message readable | Role management / invite screens |

### 7.5 Demo path

1. Owner/analyst: bind postgres_ro + run → Trace OK  
2. Viewer: can open Trace of existing Run; **cannot** create Run / bind  
3. Analyst: cannot bind? (should can) — show matrix  
4. Cancel: viewer 403; creator OK  

Optional: seed or document how to set a member role to `viewer` (SQL/admin) without Invite UI.

---

## 8. Explicit non-goals (M5)

| Do not |
|--------|
| IAM / SSO / OIDC / SAML |
| Invite / email onboarding / org units |
| Enterprise user directory sync |
| Fine-grained column/row security |
| Permission UI product / policy editor |
| Kernel-side authorization |
| Reopening M4 Audit productization |

---

## 9. Acceptance criteria (Definition of Done)

- [ ] Single permission helper drives Dataset + Plane + Run checks  
- [ ] viewer: read Dataset/Run/Trace; cannot upload/bind/create Run  
- [ ] owner/analyst: bind postgres_ro + run file/postgres_ro  
- [ ] cancel: creator \| owner unchanged (or documented if analyst-creator clarified)  
- [ ] skill.invoke reserved (data.bi only via run.create)  
- [ ] M4 Trace APIs still work under same visibility rules  
- [ ] M1–M3 regression: data.bi, duckdb/postgres_ro, timeout/cancel semantics unchanged  
- [ ] No IAM/SSO/Invite surfaces  

---

## 10. Open points for confirmation before coding

1. **Viewer Analyze:** confirm **cannot** create Run (recommended)?  
2. **Viewer upload:** confirm **cannot** upload file datasets?  
3. **Run visibility:** confirm **workspace-wide** for all members (option A)?  
4. **Per-dataset ACL:** role matrix only (recommended) vs `access_level` stretch?  
5. **Hide vs 403:** 404 for unauthorized get (hide existence) vs 403 (clearer Demo)? Recommend **403** for mutate; keep **404** for cross-workspace only.  
6. **How to create viewer in Demo:** document SQL/`role` update only (no invite)?  

---

## 11. One-line summary

> M5 makes **Authorized Resource Access** explicit and thin: Workspace roles gate Dataset / Data Plane / Run (and reserve Skill), completing Run → Trace → Authz — without building IAM.
