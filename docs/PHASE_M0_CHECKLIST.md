# Phase M0 — Checklist (design only)

**Goal:** Freeze Enterprise Data Agent Platform charter + contracts before M1 coding.  
**Status:** ✅ Complete (2026-07-21)

## Confirmed principles

- [x] Platform name = **Enterprise Data Agent Platform**
- [x] Platform = Kernel; Skill = **`data.bi`**; shell = Workspace/Task/UI
- [x] ChatBI is not the platform definition
- [x] RepoPilot = Engineering Agent; this repo = Data Agent platform
- [x] Code domain: current strategy out; no Code Agent here; Kernel stays extensible
- [x] M1 = architecture work, no new business domain

## Deliverables

- [x] [PLATFORM_CHARTER.md](./PLATFORM_CHARTER.md)
- [x] [PLATFORM_CONTRACTS.md](./PLATFORM_CONTRACTS.md)
- [x] [PHASE_M1_CHECKLIST.md](./PHASE_M1_CHECKLIST.md) (implementation plan, coding later)
- [x] [PHASES.md](./PHASES.md) updated with M0/M1 track
- [x] Root README pointer to platform positioning

## Adjustments locked in contracts

- [x] Tool registry = minimal real call chain only
- [x] Audit = extend steps/JSON; no new audit system
- [x] Frontend = minimal Demo; no Tasks redesign
- [x] Connector abstraction deferred; DuckDB stays
- [x] `result_json.platform` optional (non-blocking)
- [x] skill traces: API/RunResult first

## Exit criteria

- [x] Naming and boundaries unambiguous
- [x] Run/Artifact/Tool/Policy/Skill frozen
- [x] Facade path `run_analysis` → `kernel.run("data.bi")` specified
- [x] Ready for M1 coding (after explicit confirmation to implement)
