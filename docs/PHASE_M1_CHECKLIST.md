# Phase M1 — Checklist (architecture migration)

**Prerequisite:** M0 complete ([PHASE_M0_CHECKLIST.md](./PHASE_M0_CHECKLIST.md))  
**Status:** ✅ Implemented — see [PHASE_M1_ACCEPTANCE.md](./PHASE_M1_ACCEPTANCE.md)

**Goal:** ChatBI Application → Enterprise Data Agent Platform + Skill `data.bi`  
**Not a goal:** New business domain features; pure folder moves without perceivable Kernel concepts.

Contracts: [PLATFORM_CONTRACTS.md](./PLATFORM_CONTRACTS.md) · Charter: [PLATFORM_CHARTER.md](./PLATFORM_CHARTER.md)

---

## Scope locks (from confirmation)

| Do | Don't |
|----|--------|
| Kernel + Skill registry + Facade | Second skill / Code Agent |
| Minimal Tool registry (real chain) | Empty/abstract tools |
| Policy `sql.select_gate` mandatory | Bypass Gate / weaken `run_select` |
| Extend `agent_run_steps` / JSON | New audit tables/system |
| Stable API/RunResult fields (`skill_id`, …) | Large Tasks UI redesign |
| Keep Postgres / Redis / DuckDB / Worker | Complex Connector framework |
| Legacy `result_json` projection | Break golden path |
| Optional `result_json.platform` | Block M1 on that field |

---

## Steps

### M1.0 Baseline

- [x] Record golden path + run existing smokes as regression baseline

### M1.1 Kernel boundary

- [x] `agent/kernel/` types: RunRequest, RunResult, Artifact, ToolCall, PolicyDecision
- [x] `kernel.run(RunRequest) -> RunResult`
- [x] Skill / Tool / Policy registries (minimal)
- [x] Facade: `run_analysis` → `kernel.run(skill_id="data.bi")` → project `result_json`

### M1.2 Skill `data.bi`

- [x] Register only `data.bi`
- [x] Existing graph as skill implementation (wrap)
- [x] `RunResult.skill_id == "data.bi"`

### M1.3 Tools + Policy (perceivable)

- [x] Register real tools only
- [x] `sql.execute_select` always via `sql.select_gate`
- [x] Persist traces via steps `output_json` and RunResult fields
- [x] Artifacts assembled + projected to legacy `result_json`

### M1.4 Worker / shell (minimal)

- [x] Worker still uses Facade; no direct graph imports
- [x] Auth / Workspace / Dataset / Redis semantics unchanged
- [x] mock \| agent still works
- [x] Optional: `result_json.platform`

### M1.5 Docs / Demo narrative

- [x] README = Enterprise Data Agent Platform + data.bi + RepoPilot contrast
- [x] agent README = Kernel vs Skill
- [x] `PHASE_M1_ACCEPTANCE.md`

### M1.6 Frontend (minimal Demo only)

- [x] Show `skill_id` (+ tool/policy hint)

---

## Acceptance (DoD)

- [x] Golden path: upload → analyze → SQL / table / chart / report (smoke)
- [x] `kernel.run` works for `data.bi`
- [x] `data.bi` registered
- [x] SQL Policy not bypassable; defense-in-depth `run_select` remains
- [x] Platform concepts explainable in Demo + README
- [x] Smokes green; frontend build passes
- [x] No new business domain; no Code Agent in this repo
