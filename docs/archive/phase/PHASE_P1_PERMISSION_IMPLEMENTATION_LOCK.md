# P1 Permission / Governance — Implementation Lock

**Status:** Confirmed for coding (2026-07-22)  
**Parent checklist:** [PHASE_P1_PERMISSION_GOVERNANCE_CHECKLIST.md](PHASE_P1_PERMISSION_GOVERNANCE_CHECKLIST.md)

## 1. Migration design

**Revision:** `0011_p1_dataset_acl`  
**Table:** `dataset_acl`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `workspace_id` | UUID FK → workspaces | indexed |
| `dataset_id` | UUID FK → datasets ON DELETE CASCADE | |
| `user_id` | UUID FK → users ON DELETE CASCADE | |
| `can_read` | BOOLEAN NOT NULL DEFAULT true | |
| `can_run` | BOOLEAN NOT NULL DEFAULT false | |
| `created_at` | timestamptz | server default now |

**Constraints:** `UNIQUE (dataset_id, user_id)`  
**Compat:** Zero rows for a dataset ⇒ M5 behavior (role-only).

## 2. ACL check insertion points

```text
Shell only (permissions.py + services/routes)

dataset.list          → filter by can_read_dataset
dataset.get/preview   → require can_read_dataset
dataset ACL GET/PUT   → owner only
run.create            → require can_run_dataset (+ mutator)
run.list/get/…        → require can_read on task.dataset (or creator/owner)
artifact.list/get     → same as run read
```

**Not inserted into:** Kernel, Gate, Skill graph, Worker execution path (Worker only **echoes** authorization onto Trace).

**Split:**

- ACL = may the user touch this Dataset / Run?  
- Policy Gate = may this SQL run?

## 3. Trace field structure

```json
"platform": {
  "authorization": {
    "actor_user_id": "<uuid>",
    "actor_role": "owner|analyst|viewer",
    "dataset_id": "<uuid>",
    "authorized_tables": ["…"],
    "acl_mode": "default_open" | "acl_restricted"
  }
}
```

- Audit / explain only for that Run  
- **Not** a permission cache; live ACL queries remain source of truth  
- `authorized_tables` from `allowed_tables_for(dataset)` (same list Policy sees)

## 4. Smoke / release gate acceptance

`smoke_p1_permissions.py` must prove:

1. No ACL rows → M5-equivalent (viewer cannot run; can get dataset)  
2. Owner always read/run  
3. With ACL on dataset A: viewer without grant → get 403; with `can_read` → ok  
4. Analyst without `can_run` → create_task 403  
5. Analyst with `can_run` → create allowed (enqueue may hit Redis)  
6. Result/platform authorization shape when Worker path materializes (or unit helper builds dict)

Wire into `smoke_release_gate.py` after M5 smoke (or replace extension — keep `smoke_m5_permissions` + add P1).

## 5. Frontend

- List datasets from API (already filtered server-side)  
- No ACL admin UI in P1
