# M3 Value Ranking — post-M2

**Context:** M1 (Platform + Skill) + M2 (Governed Runtime) are frozen.  
**Question:** Which next theme most strengthens **Enterprise Data Agent Platform**?

Candidates (user-requested):

1. **Connector** — read-only external datasource (thin slice)  
2. **RBAC** — resource-level access  
3. **Audit enhancement** — beyond steps / platform traces  

---

## Scoring criteria (same weights as M2 ranking)

| Criterion | Weight |
|-----------|--------|
| A. Platform positioning lift | 35% |
| B. Complementarity vs RepoPilot | 25% |
| C. Demo / resume narrative | 25% |
| D. Controllability (lower risk/cost → higher) | 15% |

Scores 1–5.

---

## 1. Connector (read-only external source)

**Story:** Same Kernel + Policy + governed Run, data not only DuckDB files.

| Criterion | Score | Notes |
|-----------|-------|-------|
| A Positioning | **5** | Proves Data plane depth; “enterprise data agent” not file-demo-only |
| B vs RepoPilot | **5** | Max domain distance from Engineering Agent |
| C Demo | **4** | Strong if one Postgres read-only + Policy allowlist; needs fixture DB |
| D Controllability | **2** | Secrets, network, dialect, allowlist, blast radius on M1/M2 freeze |
| **Weighted** | **≈ 4.30** | |

**M3 shape if chosen (thin slice):**  
One read-only Postgres schema/table allowlist → still `sql.select_gate` → same `data.bi` or tiny skill variant → no multi-source UI sprawl.

**Risk:** Narrative drifts to “BI/ETL tool” if Connector framework is overbuilt.

---

## 2. RBAC (resource-level)

**Story:** Runs/datasets are authorized resources, not only workspace membership.

| Criterion | Score | Notes |
|-----------|-------|-------|
| A Positioning | **3** | Enterprise credibility; weak Agent-kernel story vs Connector/Audit |
| B vs RepoPilot | **3** | Generic SaaS capability; less distinctive complementarity |
| C Demo | **2** | Hard to “show”; denial screens weaker than SQL→chart→timeout |
| D Controllability | **4** | Can extend creator/owner checks; invite UI still forbidden |
| **Weighted** | **≈ 2.90** | |

**Better as companion:** tighten cancel/dataset checks when Connector lands (who may attach credentials / run against which source).

---

## 3. Audit enhancement

**Story:** Stronger traceability of Tool/Policy/Run decisions.

| Criterion | Score | Notes |
|-----------|-------|-------|
| A Positioning | **4** | Governance narrative pairs with M2; “governed agent” depth |
| B vs RepoPilot | **4** | Symmetric to RepoPilot audit/safety story, different domain |
| C Demo | **3** | Good for interview deep-dive; less visual than Connector |
| D Controllability | **3** | Easy to overbuild (new tables/service); M1 said no audit product |
| **Weighted** | **≈ 3.65** | |

**M3 shape if chosen (thin):**  
Query API or export of `agent_run_steps` + `failure_class` + `platform.run/tool/policy`; optional filter by `failure_class=policy_denied`. **No** new audit microservice.

---

## Ranking

| Rank | Theme | ≈ Score | Role |
|------|-------|---------|------|
| **1** | **Connector (read-only thin slice)** | **4.30** | **Recommended M3 theme** |
| **2** | Audit enhancement (thin) | 3.65 | Strong alternate / M3b |
| **3** | RBAC (phase theme) | 2.90 | Companion only |

---

## Recommendation

### Preferred M3: Connector thin slice

**Why now:**  
Runtime governance (M2) is in place — safe to attach a **second data plane** without confusing “lifecycle” with “integration.” Maximizes Data Agent vs RepoPilot contrast.

**Guardrails:**

- One source type (e.g. read-only Postgres)  
- Credentials in env/workspace secret minimal store — not a vault product  
- All queries still through Policy + existing execute path patterns  
- No multi-connector framework / no write connectors  
- Keep `/tasks` API; keep M1/M2 behaviors  

### Alternate M3: Audit thin slice

Choose if Demo environment cannot host an external DB, or interview focus is governance symmetry with RepoPilot.

### Not M3 theme: RBAC

Fold light resource checks into Connector work; do not open an IAM phase.

---

## Suggested sequence (still design-gated)

```text
Now     M1 + M2 frozen
        ↓ confirm
M3      Connector thin slice (+ light resource checks as companion)
        ↓ optional
M3b     Audit query/export thin slice
```

---

## Decision (confirmed)

**M3 = Connector thin slice (Postgres read-only + Policy mandatory).**

- Not a connector/ETL product — proves multi-plane Runtime with unchanged Policy / Run governance  
- Design checklist: `PHASE_M3_CHECKLIST.md` (coding only after checklist confirmation)  
- Audit thin → candidate **M3b**; RBAC remains companion-only  
- M1/M2 remain frozen
