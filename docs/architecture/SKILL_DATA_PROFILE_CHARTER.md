# Skill Charter — `data.profile`

**Status:** Wave 3 (P2) — authorized thin slice  
**Skill ID:** `data.profile`  
**Purpose:** Prove the Kernel hosts **≥2** Data Skills under the same contracts (not a second product).

## Contract (same as `data.bi`)

| Concern | Rule |
|---------|------|
| Entry | `kernel.run(RunRequest(skill_id="data.profile", ...))` |
| Tools | Registered tools only; SQL goes through `sql.execute_select` + `sql.select_gate` |
| Lifecycle | `SKILL_DATA_PROFILE_ENABLED` / `SKILL_DATA_PROFILE_VERSION` (Settings → registry) |
| Trace | Steps + `platform.execution` + Artifacts |
| Worker | Dispatches by `AnalysisTask.skill_id`; no skill-specific Worker forks |

## Behavior (MVP)

Deterministic **dataset profile** over the bound Data Plane:

1. Load schema / primary table from RunRequest  
2. For up to N columns, run Policy-gated `SELECT` aggregates (`COUNT`, `COUNT(DISTINCT …)`)  
3. Emit summary + structured profile artifact + short markdown report  
4. **No free-form ReAct**; optional LLM only for narrative polish (MVP: heuristic text, no LLM required)

## Non-goals

- Not a Catalog / ETL / Connector Framework  
- Not Multi-Agent orchestration  
- Not Code Agent / RepoPilot domain  

## Acceptance

- Registry lists `data.bi` and `data.profile`  
- Disable via Settings → enqueue 403  
- Eval / smoke covers Gate-on-profile SQL + success path on file fixture  
