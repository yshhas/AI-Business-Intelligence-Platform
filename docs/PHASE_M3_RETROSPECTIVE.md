# Phase M3 — Freeze + Retrospective

**Status:** ✅ **Formally closed / frozen** (2026-07-22)

## Narrative completed

```text
M1: ChatBI Application → Platform + Skill (data.bi)
    Kernel · Skill · Tool · Policy · Artifact

M2: Platform → Governed Runtime
    timeout · cancel · failure_class

M3: Governed Runtime → Governed Data Plane
    file (DuckDB) · postgres_ro · same Policy / Run governance
```

**Proof (not a connector product):**
> Enterprise Data Agent Runtime 可以跨数据平面运行，同时保持 Policy 与 Run Governance 一致。

---

## Freeze (do not expand now)

| Do not |
|--------|
| Connector Framework / plugin registry in Kernel |
| Multi-datasource management / marketplace |
| Data Catalog / schema auto-discovery product |
| Write connectors / CDC / sync / ETL |
| Second Skill / Multi-Agent |
| Celery / Retry engine |
| Standalone Audit service (candidate only after story review) |
| Invite / enterprise IAM |

M1 + M2 + M3 remain **frozen**. Next step is architecture / story review before any M4.

---

## Retrospective

### 1. Did M3 strengthen platform positioning without weakening Kernel?

**Verdict: Yes.**

| Kept frozen | How M3 respected it |
|-------------|---------------------|
| Kernel | Still dispatch-only; no Connector Registry |
| `data.bi` graph | Same Skill; prompt/allowlist plumbing only |
| Tool contract | `sql.execute_select` + injected callback |
| Policy | `sql.select_gate` mandatory before both executors |
| Run lifecycle | Still Worker-owned; `connector_error` additive only |

Branch point stayed where M1 deferred it: **Product Shell `execute_select`**.

### 2. Is “thin Connector” enough as a Data Plane v1?

**Verdict: Yes, as a proof — not as a product.**

| Strength | Why |
|----------|-----|
| Two planes | `file` + `postgres_ro` |
| Same Policy | Allowlist + SELECT-only on both |
| Same Run | timeout / cancel / `failure_class` unchanged ownership |
| Isolation story | Platform `DATABASE_URL` ≠ `POSTGRES_RO_DSN` |
| Controllable surface | Env DSN, ≤2 `public.*` tables, thin bind API |

| Gap (acceptable) | Note |
|------------------|------|
| `duckdb_table` name for Postgres primary | Intentional freeze; rename later if needed |
| Cooperative cancel vs in-flight PG query | Same class of limit as DuckDB (document) |
| Single `connection_ref=default` | Not a secret manager |

**Recommendation:** Do **not** open a Connector Framework phase. Treat current RO bind as **Data Plane v1 proof**.

### 3. Did M3 improve complementarity vs RepoPilot?

**Verdict: Yes — clearest domain distance so far.**

| RepoPilot | This platform (post-M3) |
|-----------|-------------------------|
| Engineering change governance | Data access + analysis governance |
| Code / Git plane | File + enterprise SQL read plane |
| Shared: tools, policies, run honesty | Shared thought; different substrate |

### 4. What stays deferred after M3?

| Capability | Stay deferred? | Why |
|------------|----------------|-----|
| Connector Framework | **Yes** | Would dilute “Runtime proof” into integration product |
| Audit thin enhancement | Candidate for ranking | Governance symmetry; Demo weaker than Connector was |
| RBAC companion | Companion only | Bind/run owner\|analyst already exists |
| Artifact/Report depth | Candidate | Product polish; weaker Kernel story |
| Second Skill | **Yes** | Premature; one Skill already proved multi-plane |
| Stay frozen (docs/Demo only) | Always an option | If resume narrative is already complete |

---

## Architecture boundary reminder (post-M3)

```text
Product Shell (API / Dataset bind / Auth companion)
        |
Worker / Task Lifecycle     ← timeout, cancel, failure_class (+ connector_error)
        |
Kernel.run                  ← Skill dispatch only
        |
Skill(data.bi)
        |
Tool(sql.execute_select)
        |
Policy(sql.select_gate)
        |
Executor: DuckDB | Postgres RO    ← Data Plane (M3)
```

**Forbidden shapes (still):** Connector in Kernel · bypass Policy · executor owns Run lifecycle.

---

## Docs follow-ups from this freeze

1. Update [PLATFORM_CHARTER.md](./PLATFORM_CHARTER.md) — Data Plane + M3 limitations  
2. [PLATFORM_STORY_REVIEW.md](./PLATFORM_STORY_REVIEW.md) — Demo arc + Charter check  
3. [M4_VALUE_RANKING.md](./M4_VALUE_RANKING.md) — next theme ranking (decision-gated)

---

## One-line freeze summary

> M3 proved a **Governed Data Plane**: one Skill, one Policy, one Run model — on file **or** Postgres read-only — without becoming a connector platform.
