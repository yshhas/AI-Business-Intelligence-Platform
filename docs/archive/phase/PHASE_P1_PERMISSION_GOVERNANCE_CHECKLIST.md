# P1 — Permission / Governance Deepen Design Checklist

**Status:** ✅ Implemented — see [PHASE_P1_PERMISSION_ACCEPTANCE.md](PHASE_P1_PERMISSION_ACCEPTANCE.md) · [IMPLEMENTATION_LOCK](PHASE_P1_PERMISSION_IMPLEMENTATION_LOCK.md)  
**Date:** 2026-07-22  
**Parents:** [PROJECT_IMPROVEMENT_PLAN.md](../roadmap/PROJECT_IMPROVEMENT_PLAN.md) · [PHASE_M5_ACCEPTANCE.md](PHASE_M5_ACCEPTANCE.md) · P0-1/P0-2 frozen  
**Architecture lock:**

```text
Product Shell (Permission)  →  Worker / Run  →  Kernel  →  Skill  →  Policy  →  Plane  →  Trace
```

**Rule:** Permission stays in the **Shell**. Kernel / Skill / Policy / Worker do **not** import RBAC for execution decisions. Policy `sql.select_gate` remains the SQL allow/deny authority.

---

## 0. Goal

Deepen governance from M5’s **workspace + role** matrix to a thin **resource-aware** story:

```text
Today (M5):
  workspace membership + role
    → any member sees all Datasets / Runs in workspace
    → mutators can Analyze any ready Dataset

P1 target (thin):
  workspace
    → member role
    → Dataset ACL (who may read / run this Dataset)
    → authorized_tables (echo allowlist already bound on Dataset)
    → Trace explains actor_role + authorized_tables
```

**Not the goal:** tenant trees, SSO/IAM suites, column ABAC engines, Invite/org products.

**Motto:** make authorization **explainable and dataset-scoped** — without becoming an IAM company.

---

## 1. As-is (M5) — keep and extend

| Asset | Location | Behavior |
|-------|----------|----------|
| Role matrix | `permissions.py` | owner / analyst / viewer |
| Mutators | upload, bind postgres_ro, Analyze | owner\|analyst |
| Readers | list/get Dataset, Run, Trace, Artifact | any workspace member |
| Cancel | creator \| workspace owner | unchanged |
| Errors | 403 in-workspace; 404 cross-workspace | keep |
| Kernel | untouched | keep |

### Gaps this phase closes

| Gap | Why it matters |
|-----|----------------|
| All members see all Datasets | Cannot Demo “sensitive dataset hidden from viewer X” |
| All mutators can Analyze all Datasets | No dataset-scoped run grant |
| Trace lacks actor/authorization narrative | Permission ↔ Policy story is split |
| Allowlist exists on Dataset but not echoed as “authorized” on Trace | Governance Demo incomplete |

---

## 2. Proposed thin model

### 2.1 Compatibility default (critical)

```text
If a member has no Dataset ACL rows:
  → behavior identical to M5 (full workspace visibility for their role)
```

ACL is **additive restriction**, not a greenfield break. Owner always retains full access (implicit).

### 2.2 Dataset ACL (recommended shape)

**Table:** `dataset_acl` (name TBD)

| Column | Type | Meaning |
|--------|------|---------|
| `id` | UUID PK | |
| `workspace_id` | UUID FK | denormalized for query ease |
| `dataset_id` | UUID FK | |
| `user_id` | UUID FK | member being granted |
| `can_read` | bool | list/get/preview (and derived Run read if run on this dataset) |
| `can_run` | bool | Analyze / skill.invoke on this dataset |
| `created_at` | timestamptz | |

**Constraints:** unique `(dataset_id, user_id)`; user must be workspace member (enforced in service).

**Semantics:**

| Role | ACL interaction |
|------|-----------------|
| **owner** | Implicit full read+run on all workspace datasets (ignore ACL deny) |
| **analyst** | If any ACL rows exist **for this dataset**, require `can_run` / `can_read`; if **no rows** for dataset → M5 (all analysts OK) |
| **viewer** | If ACL rows exist for dataset → need `can_read`; if none → M5 (all viewers can read) |

**Alternative (stricter, not default):** “ACL mode” flag per workspace — **out** of P1 to avoid config product.

**Grant API (thin):** owner-only endpoints:

- `PUT/PATCH .../datasets/{id}/acl` — replace or upsert grants for listed users  
- `GET .../datasets/{id}/acl` — list grants  

No Invite UI; grant existing workspace members only.

### 2.3 Run / Trace visibility

| Action | Rule |
|--------|------|
| `dataset.list` | Filter to datasets member may read (owner=all; else ACL∪default) |
| `dataset.get/preview` | Require read |
| `run.create` / `skill.invoke` | Require run on that dataset (+ mutator role) |
| `run.list/get/execution/steps/artifacts` | Allow if member can **read the task’s dataset** (or is creator/owner) |

Cross-workspace still **404** via membership.

### 2.4 Table allowlist ↔ Policy narrative

**Already true:** `dataset_service.allowed_tables_for(dataset)` feeds Gate.

**P1 add (Shell / Trace only):**

When materializing Execution Trace / `platform.run` (Worker or task_service projection):

```json
"authorization": {
  "actor_user_id": "...",
  "actor_role": "analyst",
  "dataset_id": "...",
  "authorized_tables": ["ds_…"] | ["public.demo_orders", ...]
}
```

- Sourced from membership role + `allowed_tables_for`  
- **Does not** change Gate logic  
- Makes Permission ↔ Policy Demoable on Trace UI (minimal field display OK; no ACL admin UI required in P1 if API-only grants)

### 2.5 What we explicitly do **not** add

| Out | Reason |
|-----|--------|
| Tenant / Org | Charter / overbuild |
| SSO / SCIM / Invite suite | M5 freeze spirit |
| Column-level / row-level ACL product | Use DB RO role; optional Gate column denylist is P2+ |
| Kernel imports permissions | Boundary break |
| Policy-as-code / ABAC engine | Ceremony without second policy family |
| Per-skill IAM | Single skill `data.bi` |

---

## 3. Action matrix delta (vs M5)

| Action | M5 | P1 |
|--------|----|----|
| `dataset.list` | all in workspace | filtered by read ACL (compat default) |
| `dataset.get/preview` | any member | read ACL |
| `dataset.create_file` / bind | mutator | **unchanged** (+ new dataset inherits “no ACL = open”) |
| `run.create` | mutator + ready dataset | mutator + **can_run** |
| `run.*` read paths | any member | read on task.dataset (or creator/owner) |
| `run.cancel` | creator\|owner | **unchanged** |
| `artifact.*` | follow run | follow run read |

---

## 4. Code impact scope (planned)

### In scope

| Path | Change |
|------|--------|
| `alembic/versions/0011_*.py` | `dataset_acl` table |
| `models` | `DatasetAcl` |
| `permissions.py` | ACL-aware `can` / helpers `can_read_dataset` / `can_run_dataset` |
| `dataset_service` / `routes_datasets` | list filter; get/preview require; ACL get/put (owner) |
| `task_service` / routes | create + list/get filters |
| `artifact_service` | inherit run/dataset read |
| Worker or result projection | `platform.authorization` echo |
| `smoke_p1_permissions.py` | extend beyond M5 |
| Frontend (thin) | optional: hide datasets user cannot see; ACL admin can be API-only for P1 |
| Docs | acceptance / OPS note |

### Out of scope

| Item | Why |
|------|-----|
| Kernel / Gate algorithm change | Policy already has allowlist |
| Cost UI / budget ACL coupling | Separate concerns |
| Eval suite expansion for ACL | Optional companion smoke only |
| Full ACL management UX | Can defer UI to thin follow-up if API ships first |

---

## 5. Trace / Observability

| Field | Where | Purpose |
|-------|-------|---------|
| `actor_role` | `platform.authorization` | Who ran |
| `actor_user_id` | same | Audit-shaped |
| `authorized_tables` | same | Aligns with Gate allowlist |
| `dataset_id` | same | Resource pointer |

Existing M4 filters (`skill_id`, `policy_denied`, …) unchanged.  
**Not** a new Audit microservice.

---

## 6. Error & Demo contract

| Case | HTTP | Notes |
|------|------|-------|
| In-workspace, ACL deny | **403** | Stable message |
| Not a member | **404** | Unchanged |
| Owner bypass | always allow | Documented |
| Empty ACL on dataset | M5 behavior | Compat |

**Demo script (target):**

1. Owner grants viewer read-only on Dataset A; no grant on Dataset B  
2. Viewer lists → sees A only; get B → 403  
3. Analyst without `can_run` on A → Analyze 403  
4. Successful Run Trace shows `authorization.authorized_tables`  

---

## 7. Acceptance criteria (for later implement)

- [ ] Migration + model for Dataset ACL  
- [ ] Default (no ACL rows) ≡ M5 behavior  
- [ ] Owner implicit full access  
- [ ] Viewer/analyst restricted when ACL rows present for that dataset  
- [ ] `run.create` checks `can_run`  
- [ ] List/get Run/Trace/Artifact respect dataset read (or creator/owner)  
- [ ] Trace carries `platform.authorization` with role + authorized_tables  
- [ ] Kernel / Policy Gate code paths unchanged (allowlist still from Dataset bind)  
- [ ] Smoke covers grant / deny / compat default / owner bypass  
- [ ] No SSO / Invite / tenant / column ACL product  

---

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Breaking existing Demos | Compat default when ACL empty |
| ACL complexity creep | Single table; two booleans; owner-only grants |
| Confusing Permission vs Policy | Trace `authorized_tables` documents the bridge; Gate still decides SQL |
| Frontend lag | API-first OK; minimal list filtering if timeboxed |
| Performance | Index `(user_id, dataset_id)`; small Demo cardinality |

---

## 9. Relationship to Roadmap

| Phase | Role |
|-------|------|
| **M5** | Workspace + role (frozen) |
| **P0-1 / P0-2** | Eval + soft cost (frozen) |
| **P1 Permission** | Dataset ACL + Trace authorization echo (**this checklist**) |
| **P1-1/1-2 SQL quality** | Separate; do not mix into this phase |
| **P1-4 Cost rollup UI** | Separate |
| **Later** | Column denylist Gate · tenant — only with hard triggers |

**Suggested implement order inside P1 Permission (after confirm):**

1. Schema + `permissions.py` helpers + compat tests  
2. Enforce on Dataset/Run APIs  
3. Trace `authorization` projection  
4. Owner ACL API + smoke  
5. Optional minimal UI filter  

---

## 10. Decision gate (human)

| Option | Meaning |
|--------|---------|
| **Confirm as written** | Implement Dataset ACL + Trace authorization; API-first ACL admin |
| **Confirm API-only (no frontend ACL UI)** | Same backend; UI only hides inaccessible datasets if easy |
| **Defer Trace authorization fields** | ACL enforce only (weaker Demo — not recommended) |
| **Reject / revise** | e.g. member-level allowlist JSON instead of `dataset_acl` table |

**Awaiting confirmation — no coding until approved.**
