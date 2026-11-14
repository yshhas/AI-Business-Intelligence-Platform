# Phase M1 — Freeze + Retrospective

**Status:** ✅ **Formally closed** (2026-07-21)  
**After:** real-env E2E + policy-before-DuckDB verification

## Real-env verification

| Check | Result |
|-------|--------|
| Restart API + Worker | OK |
| `/health` platform registry | `enterprise-data-agent`, skills=`data.bi`, policy=`sql.select_gate` |
| Upload → Analyze → SQL → table/chart/report | `E2E_GOLDEN_OK` (`succeeded`, 7 steps) |
| `result_json.platform.skill_id` | `data.bi` |
| artifacts (via projection) | summary/sql/table/charts/report present |
| tool_ids in platform | generate/validate/execute/chart/report |
| policy_ids | `sql.select_gate` |
| steps enriched | `tool_id` / `policy_id` / `skill_id` on nodes |
| Illegal SQL before DuckDB | `POLICY_BLOCK_OK` (`duckdb_hits=0`) |

## Freeze (do not expand in this phase)

- No second Skill
- No Connector framework
- No standalone Audit system
- No multi-agent
- No large UI redesign

## Retrospective (for M2 decision)

### Kernel boundary — reasonable?

**Yes, for current scale.** Kernel owns: `run`, registries, Run/Artifact/Tool/Policy types, Facade projection.  
Skill owns: BI graph. Product shell owns: Auth/Workspace/Dataset/Redis/Worker.  
DuckDB stays behind injected `execute_select` (no premature Connector).

### Abstractions that proved real (keep)

| Abstraction | Why real |
|-------------|----------|
| `skill_id` + Skill registry | Demo/API can name the capability; enables future skills without renaming the app |
| `kernel.run` + `run_analysis` Facade | Zero Worker rewrite; dual entry for tests |
| Policy on `sql.execute_select` | Makes Gate a platform concept; verified not to hit DuckDB on reject |
| Artifact → `result_json` projection | Keeps React contract stable |
| Minimal Tool registry (real chain) | Traces without empty interfaces |
| steps `output_json` enrichment | Audit-lite without new tables |

### Defer (not needed yet)

| Item | Why defer |
|------|-----------|
| Second Skill | No product demand; risks hollow platform |
| Connector interface | One DuckDB path; abstraction would be speculative |
| Independent Audit service/tables | steps + RunResult traces enough |
| Run cancel/timeout/idempotency (M2 candidate) | Ops pain not blocking Demo yet |
| Resource-level RBAC beyond owner checks | Invite/multi-user not in scope |
| Large “Runs/Artifacts” IA | Platform perception already via health + result.platform + one UI line |
| Multi-agent / second orchestrator | Explicitly rejected |

### Risks to watch (not blockers)

- LLM path can slow E2E when `LLM_API_KEY` is set (still succeeded in real run)
- `tool_calls` may duplicate execute traces (node-derived + wrapper) — acceptable for M1
- Gate table extraction remains best-effort regex

## M2 decision gate (not started)

Only open M2 after choosing **one** primary theme:

1. **Run lifecycle** (timeout/cancel/failure classes), or  
2. **RBAC tightening** (resource checks, still no invite UI), or  
3. **Read-only external connector** (still Policy-bound)

Do **not** start all three. Prefer (1) if Demo ops pain appears; otherwise stay frozen and polish docs/Demo narrative.
