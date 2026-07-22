# Phase M2 Acceptance — Run Lifecycle

**Status:** ✅ Implemented (smoke-verified)  
**Date:** 2026-07-21

## Goal

```text
M1: Skill runs on the platform
M2: Run is governable (timeout / cancel / failure class)
```

## Delivered

| Capability | Implementation |
|------------|----------------|
| Timeout | `RUN_TIMEOUT_SECONDS=120` (per-task `timeout_seconds`); Worker thread+join; status `timed_out` |
| Cancel | `POST /tasks/{id}/cancel`; creator/owner; pending→`cancelled`, running→cooperative flag |
| Failure class | `failure_class` column + mapping (`policy_denied`, `timeout`, `cancelled`, …) |
| Idempotent claim | CAS `pending`→`running`; terminal skips |
| Queue | Redis List unchanged; no Celery; no auto-retry |
| UI | Cancel button + status/`failure_class` display (minimal) |

## Verified

| Check | Result |
|-------|--------|
| Alembic `0004_m2_run_lifecycle` | applied |
| `smoke_m2_lifecycle.py` | `CANCEL_PENDING_OK` / `TIMEOUT_OK` / `M2_LIFECYCLE_OK` |
| Frontend build | pass |

## Limitations (documented)

- Cooperative timeout/cancel does **not** guarantee abort of in-flight LLM HTTP or DuckDB queries.
- Failed runs are re-run by **creating a new task** (no auto-retry).

## Freeze / stop-lines held

No new Skill, Connector, Multi-Agent, Audit service, or large UI redesign.
