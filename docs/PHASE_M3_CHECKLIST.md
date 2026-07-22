# Phase M3 — Connector Thin Slice Checklist（仅设计，待确认后编码）

**Status:** 🟢 Implemented — see [PHASE_M3_ACCEPTANCE.md](./PHASE_M3_ACCEPTANCE.md)  
**Prerequisite:** M1 + M2 frozen (Platform Kernel + Governed Runtime)  
**Theme:** Read-only Postgres connector behind existing `execute_select`  
**Goal:** From “file-demo Data Agent” → “same Runtime on an enterprise data plane”

**Confirmed open points (2026-07-22)**
| # | Decision |
|---|----------|
| 1 Bind | Thin API + minimal config (not seed-only) |
| 2 DSN | Single env `POSTGRES_RO_DSN`; separate from `DATABASE_URL`; no vault |
| 3 Field | Keep `duckdb_table` as primary relation name |
| 4 Allowlist | Demo fixed ≤2 tables (`source_config_json`) |
| 5 failure_class | Single `connector_error` |
| 6 Gate names | Schema-qualified `public.table_name` only for postgres_ro |
| 7 Demo DB | Separate RO Postgres from platform DB |

**Narrative**
```text
M1: ChatBI → Platform + Skill (data.bi)
M2: Agent Run → Governed Runtime (timeout / cancel / failure_class)
M3: Data Agent → 企业数据平面扩展（Postgres RO + Policy 不变）
```

**Proof target (not a connector product):**
> 同一个 Enterprise Data Agent Runtime，可以在不同数据面上运行，并且 Policy / Run Governance 保持一致。

**Hard stop-lines**
- M1/M2 contracts & boundaries remain frozen
- No Connector Framework / multi-source product / write path / CDC / sync / Catalog
- No second Skill / Multi-Agent / Celery / Retry Engine / Audit service
- Connector must not enter Kernel, must not bypass Policy, must not own Run lifecycle

---

## 0. Architecture invariant (do not break)

```text
Product Shell (API / Dataset / Auth)
        |
Worker / Task Lifecycle          ← M2: timeout, cancel, failure_class
        |
Kernel.run                       ← M1: dispatch only
        |
Skill(data.bi)
        |
Tool(sql.execute_select)
        |
Policy(sql.select_gate)          ← mandatory, before any engine
        |
Data executor (DuckDB | Postgres RO)   ← M3: branch here only
```

**Forbidden shapes**
| Anti-pattern | Why |
|--------------|-----|
| Connector Registry inside `agent/kernel` | Breaks Kernel = Skill execution only |
| Postgres path skipping `tool_execute_select` / Gate | Breaks Policy-first story |
| Connector managing timeout/cancel | Lifecycle stays in Worker |
| New Skill just to “do Postgres” | Premature; same `data.bi` must prove multi-plane |

---

## 1. Current DuckDB data path (as-is)

### 1.1 End-to-end flow

```text
Upload CSV/XLSX
  → dataset_service.create_dataset_from_upload
       source_type = "file" (hardcoded)
       storage_path + duckdb_table (ds_*)
  → duckdb_service.import_file → per-workspace DuckDB file
  → Dataset.status = ready (schema_json, row_count)

POST /tasks (dataset_id + question)
  → AnalysisTask pending → Redis List
  → Worker claim → agent_runtime.run_agent_analysis
       closes over duckdb_service.run_select(allowed_tables={duckdb_table})
       injects AnalysisContext.execute_select
  → Facade run_analysis → kernel.run(skill_id="data.bi")
  → Skill wraps execute_select with tool_execute_select
       → Policy sql.select_gate
       → inner_execute → duckdb_service.run_select
            → Gate again (defense in depth)
            → duckdb.connect(..., read_only=True)
```

### 1.2 Key modules

| Concern | Location | Note |
|---------|----------|------|
| Dataset create | `backend/app/services/dataset_service.py` | Always `source_type="file"` today |
| Dataset model | `backend/app/models` `Dataset` | Already has `source_type` string; file-centric columns (`storage_path`, `original_filename`, `duckdb_table`) |
| DuckDB execute | `backend/app/services/duckdb_service.py` `run_select` | Gate + read_only connect |
| Injection seam | `backend/app/workers/agent_runtime.py` | **Natural M3 branch point** |
| Policy wrap | `agent/kernel/tools.py` `tool_execute_select` | Unchanged in M3 |
| SQL Gate | `agent/gates/sql_gate.py` | SELECT/WITH, allowlist, LIMIT, forbidden keywords |
| Lifecycle | Worker + `run_lifecycle.py` | Unchanged ownership |

### 1.3 What already helps M3

- `execute_select: (sql, limit) → {columns, rows, row_count, sql}` is engine-agnostic at Kernel/Skill boundary
- Policy is mandatory on the Tool path; DuckDB re-gates as defense in depth
- `Dataset.source_type` exists as a string hook (no framework needed)
- M2 `failure_class` + cooperative timeout/cancel apply regardless of executor

### 1.4 Gaps vs “enterprise data plane”

| Gap | Effect |
|-----|--------|
| Only file → DuckDB | Demo reads as ChatBI upload product |
| `agent_runtime` hardcodes DuckDB | No second plane proof |
| No external credential surface | Cannot attach live RO source safely |
| `classify_exception` has no connector errors | Connection/auth failures collapse into `skill_error` |
| File-shaped Dataset columns | Postgres RO needs minimal metadata without inventing Connector ORM |

---

## 2. Postgres readonly 接入点 (to-be)

### 2.1 Single seam (recommended)

**Only** branch in Product Shell when building `execute_select`:

```text
agent_runtime.run_agent_analysis
  dataset = load Dataset
  if dataset.source_type == "file":
      execute_select = duckdb_service.run_select(...)
  elif dataset.source_type == "postgres_ro":
      execute_select = postgres_ro_service.run_select(...)  # new, thin
  else:
      raise (unknown source_type → failure_class below)
```

Kernel, Skill graph, Tool registry, Policy registry: **no changes required** for the happy path  
(optional doc-only wording: Tool description “via DuckDB” → “via injected select executor”).

### 2.2 Postgres RO executor contract

Mirror DuckDB `run_select` shape:

| Input | Meaning |
|-------|---------|
| `sql` | Already Policy-gated by Tool; executor **must** re-apply Gate (defense in depth) |
| `allowed_tables` | From Dataset allowlist metadata |
| `default_limit` | From settings / call `limit` |

| Output | Same as DuckDB path |
|--------|---------------------|
| `columns`, `rows`, `row_count`, `sql` (normalized) | Stable for `data.bi` nodes |

### 2.3 Engine-side read-only (defense in depth)

Pick **one** primary mechanism at coding kickoff (document in acceptance):

| Option | M3 preference |
|--------|----------------|
| **A. Dedicated DB role** with SELECT-only on allowlisted tables | Preferred for Demo narrative |
| **B. Session** `SET default_transaction_read_only = on` (and/or `SET TRANSACTION READ ONLY`) | Required minimum even if role is shared |
| **C. Separate database URL** pointing at a RO replica / RO user | Strongest Demo story if fixture supports it |

**Rule:** Application Gate is not enough; engine must refuse writes even if Gate regresses.

### 2.4 What stays out of the executor

- Connection pooling product / PgBouncer config as a feature
- Schema discovery crawler / information_schema UI product
- Query planner hints / cost governor (beyond existing LIMIT)
- Dialect translation layer (LLM + Gate stay Postgres-flavored for this Dataset)

### 2.5 Schema / prompt context for `data.bi`

For `postgres_ro` Datasets, Worker still fills `AnalysisContext`:

| Field | Postgres RO source |
|-------|-------------------|
| `duckdb_table` | Reuse as **primary allowlisted relation name** (string), or document alias `primary_table` in comments only — **avoid Kernel/Skill rename in M3** |
| `schema` / `schema_json` | Snapshot of columns from `information_schema` (or static fixture) at Dataset bind time |
| `execute_select` | Postgres RO implementation |

**Design note:** Keeping `duckdb_table` field name is ugly but preserves M1/M2 freeze; optional later rename is **out of M3**. Document the semantic: “primary relation id for allowlist + prompting.”

---

## 3. `source_type` design

### 3.1 Enum (M3)

| Value | Meaning | Executor |
|-------|---------|----------|
| `file` | Upload → workspace DuckDB (existing) | `duckdb_service` |
| `postgres_ro` | Bound read-only Postgres relation(s) | `postgres_ro_service` (new) |

No other values in M3. Unknown → fail closed.

### 3.2 Dataset metadata (minimal additive)

Prefer **additive** columns or a small JSON blob — do **not** invent `connectors` table / registry.

**Recommended (thin):**

| Field | Change | Purpose |
|-------|--------|---------|
| `source_type` | Use `file` \| `postgres_ro` | Branch key |
| `duckdb_table` | Keep; for `postgres_ro` = allowlisted table/view name | Gate allowlist + prompt |
| `schema_json` / `row_count` | Keep; populated at bind/introspect | Prompt + UI |
| `storage_path` / `original_filename` | For `postgres_ro`: nullable **or** sentinel placeholders | Avoid forcing fake upload paths |
| `connection_ref` **or** `source_config_json` | **New optional** | Non-secret pointer: which env DSN key / which fixture profile; allowlist extras |

**Do not store raw passwords in `datasets` row.** See §4.

### 3.3 API surface (minimal)

| Flow | M3 |
|------|-----|
| Existing upload → `file` | Unchanged |
| New: bind Postgres RO Dataset | Thin API or **ops/script + admin-only route** for Demo (prefer one clear path) |
| List/get Dataset | Expose `source_type`; hide secrets |
| Create task | Unchanged path; Worker branches on `source_type` |

UI: minimal indicator (`file` vs `postgres_ro`) — no connector management console.

### 3.4 Explicit non-abstraction

```text
OK:  if source_type == "postgres_ro": ...
BAD: class Connector(Protocol): connect/discover/sync/...
BAD: connector_registry.register("postgres", ...)
BAD: Kernel.get_connector(dataset_id)
```

---

## 4. Credential 最小方案

### 4.1 Principles

- Secrets never in git, never in `result_json` / steps I/O, never echoed to UI
- M3 is **not** a vault / secret-manager product
- One Demo connection profile is enough

### 4.2 Recommended scheme

| Piece | Design |
|-------|--------|
| DSN | Env / settings, e.g. `POSTGRES_RO_DSN` (separate from app `DATABASE_URL`) |
| Dataset link | `source_type=postgres_ro` + `connection_ref="default"` (or omit if only one) + allowlisted table name |
| Auth to DB | Prefer dedicated RO role in fixture Compose |
| Rotation | Out of scope (redeploy env) |

**Alternative (acceptable if Demo needs multi-workspace isolation later):** workspace-scoped secret table with encrypted blob — **stretch; default out of M3 must-have.** Prefer single env DSN for thin slice.

### 4.3 Companion permission (not IAM)

| Action | Who (proposed) |
|--------|----------------|
| Bind / create `postgres_ro` Dataset | Workspace `owner` (or `owner`/`analyst`) |
| Create Run against `postgres_ro` Dataset | Workspace member with existing analyze rights (`owner`/`analyst`); `viewer` read-only if already so for tasks |
| View Dataset metadata | Workspace member; **no DSN** |

Invite UI / org SSO / fine-grained resource ACL matrix: **out of scope**.

### 4.4 Safety checks at bind time

- Probe connection with RO session
- Verify allowlisted table exists and is selectable
- Refuse bind if probe can write (optional smoke: `INSERT` should fail)
- Persist `schema_json` snapshot only after success

---

## 5. Policy 如何覆盖外部源

### 5.1 Same Policy, both planes

```text
validate_sql node     → sql_gate(allowed_tables)
tool_execute_select   → apply_sql_select_gate → PolicyDecision
postgres_ro.run_select → sql_gate again → READ ONLY session → execute
```

**Invariant:** There is no Postgres path that calls `cursor.execute` without passing Gate in the Tool layer **and** re-checking in the executor.

### 5.2 Allowlist semantics

| Plane | `allowed_tables` |
|-------|------------------|
| `file` | `{ dataset.duckdb_table }` e.g. `ds_<uuid>` |
| `postgres_ro` | `{ primary_table }` (+ optional fixed set in `source_config_json` if Demo needs a join of 2 fixture tables — keep ≤ small constant; no open catalog) |

Schema-qualified names: decide at coding kickoff — either force `public.foo` in allowlist or strip/normalize consistently in Gate extraction. **Document one rule; fail closed on ambiguity.**

### 5.3 Dialect / keyword notes

- Existing Gate forbidden list is DuckDB-heavy (`ATTACH`, `PRAGMA`, …) but still blocks common writes; keep as shared Gate for M3
- Optional M3 stretch: add Postgres-specific denies (`COPY … TO`, `pg_read_file`, etc.) **only if** needed for Demo threat story — not a full Postgres hardening product
- LLM prompting for `postgres_ro`: mention Postgres + allowlisted tables (Skill prompt tweak in product shell / context is OK; new Skill is not)

### 5.4 Policy denial behavior

Unchanged from M1/M2:

- Policy reject → do not hit engine
- Exhausted retries / hard deny → task `failed` + `failure_class=policy_denied`
- `result_json.platform.policies` / tool traces still present

---

## 6. `failure_class` 如何覆盖连接失败

### 6.1 Additive classes (M3)

Keep all M2 classes. Add:

| Class | Typical status | When |
|-------|----------------|------|
| `connector_error` | `failed` | DSN missing, network, auth to Postgres, relation missing at execute time, RO session setup failure, unknown `source_type` |
| `policy_denied` | `failed` | Unchanged (Gate/Policy) |
| `skill_error` | `failed` | Graph/LLM/runtime — **not** for connection failures |

Optional split (**not required** if one class is enough for Demo):

| Class | When |
|-------|------|
| `connector_auth_error` | Password/role rejected |
| `connector_unavailable` | Timeout/network to DB |

**Recommendation:** start with **one** `connector_error`; split only if Demo narrative needs it.

### 6.2 Mapping ownership

| Layer | Responsibility |
|-------|----------------|
| `postgres_ro_service` | Raise typed/`RuntimeError` with stable prefix e.g. `Connector error:` |
| `run_lifecycle.classify_exception` | Map prefix → `connector_error`; keep Policy strings → `policy_denied` |
| Worker | Unchanged terminal write path; still wraps Skill call with timeout/cancel |

### 6.3 What is **not** a connector failure

| Case | Class |
|------|-------|
| Illegal SQL / allowlist miss | `policy_denied` |
| LLM bad SQL after retries | `skill_error` or existing policy path |
| Wall clock exceeded during slow query | `timeout` (M2) — cooperative; may not cancel in-flight PG query (document limitation, same as DuckDB) |
| User cancel | `cancelled` |

### 6.4 Platform echo

On failure, `result_json.platform.run.failure_class` already exists (M2). Optionally add non-secret:

```json
"platform": {
  "run": { "...": "..." },
  "data_plane": {
    "source_type": "postgres_ro",
    "primary_table": "sales_demo"
  }
}
```

No DSN, user, host password. Stretch — nice for Demo; not blocking.

---

## 7. Demo 验收路径

### 7.1 Golden path (must)

```text
1. Fixture: Postgres with RO role + 1–2 demo tables (Compose or script)
2. Bind Dataset source_type=postgres_ro (API or seed script)
3. Create Analyze task with business question
4. Run succeeds: SQL → table/chart/report via data.bi
5. platform traces show skill/tools/policies; source_type visible in UI or result
6. Same Policy deny demo: forbidden SQL → policy_denied, engine not meaningfully relied on
7. Optional: stop Postgres → connector_error (not skill_error)
8. M2 still works on this path: timeout / cancel cooperative behavior unchanged
9. Regression: file → DuckDB golden path still green
```

### 7.2 Acceptance criteria (Definition of Done)

- [ ] `source_type=file` path unchanged (regression)
- [ ] `source_type=postgres_ro` runs through **same** `data.bi` + Policy + Worker lifecycle
- [ ] No Connector types/registry in `agent/kernel`
- [ ] Postgres executor re-applies Gate + session/role read-only
- [ ] Secrets not in DB row plaintext, steps, or API responses
- [ ] Companion auth on bind/run (thin; no IAM product)
- [ ] `failure_class=connector_error` for connection/bind/execute infra failures
- [ ] `failure_class=policy_denied` still for Gate denials on Postgres plane
- [ ] Docs: limitations (cooperative cancel vs in-flight PG query; single DSN; no multi-source)
- [ ] M1/M2 acceptance behaviors remain true

### 7.3 Suggested implementation steps (when coding starts)

| Step | Deliverable |
|------|-------------|
| **M3.0** | Spec freeze (this checklist + open points resolved) |
| **M3.1** | Fixture Postgres RO + env `POSTGRES_RO_DSN` |
| **M3.2** | `postgres_ro_service.run_select` (Gate + RO + result shape) |
| **M3.3** | Dataset bind path + `source_type=postgres_ro` metadata |
| **M3.4** | `agent_runtime` branch on `source_type` |
| **M3.5** | `failure_class=connector_error` mapping + smoke |
| **M3.6** | Companion permission checks |
| **M3.7** | Minimal UI/API indicator + Demo script |
| **M3.8** | Acceptance doc + PHASES update; M1/M2 still marked frozen |

---

## 8. Explicit non-goals (M3)

| Do not |
|--------|
| Connector Framework / plugin interface / Kernel registry |
| Multi-datasource management UI / routing / federation |
| Write connectors / INSERT-UPDATE / ETL pipelines |
| CDC / replication / scheduled sync jobs |
| Data Catalog / glossary / lineage product |
| Second Skill / Multi-Agent / Code Agent (RepoPilot domain) |
| Celery / new broker / Retry engine |
| Standalone Audit service (candidate M3b only) |
| Invite / enterprise IAM / full RBAC matrix |
| Renaming Kernel contracts or moving lifecycle into Kernel |
| Guaranteed kill of in-flight Postgres queries on cancel/timeout |

---

## 9. Open points for confirmation before coding

1. **Bind UX:** seed/script-only for Demo vs thin authenticated API?  
2. **DSN model:** confirm single env `POSTGRES_RO_DSN` (recommended) vs workspace secret stretch?  
3. **`duckdb_table` field:** keep as primary relation name (recommended for freeze) vs additive rename migration?  
4. **Allowlist:** single table only vs allow small fixed set (≤2) for one Demo join?  
5. **`failure_class`:** one `connector_error` (recommended) vs split auth/unavailable?  
6. **Schema qualification:** `public.table` vs bare `table` — pick one Gate rule?  
7. **App DB vs RO DB:** confirm RO Demo DB is **separate** from platform `DATABASE_URL` (strongly recommended)?

---

## 10. One-line summary

> M3 proves the platform is a **Data Agent Runtime**: one Skill, one Policy, one Run governance model — file/DuckDB **or** Postgres read-only — without becoming a connector/ETL product or reopening M1/M2 boundaries.
