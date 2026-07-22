# Sprint 4 Implementation Review Report

**Review date:** 2026-07-22  
**Base:** `d242bf4` · Sprint 4 changes **uncommitted**  
**Scope:** P1.4 · P1.8 ADR · v1.1 docs drafts  
**Verdict:** **PASS**  

**Not performed:** commit · push · release · tag · code changes

---

## Executive verdict

| Area | Result | Blocking? |
|------|--------|-----------|
| P1.4 hot slim | Persist-only; Trace→Artifacts→Slim order; omissions explicit | No |
| P1.8 ADR-only | Docs only; no Cookie/CSRF | No |
| Release docs | Unreleased drafts; no tag; no v2 scope | No |
| Gate / Eval / FE | Reported PASS at impl exit | No |
| Spine / Phase 2 steal-in | None | No |

**P0 / P1:** none  
**P2:** residual notes below  

---

## 1. P1.4 `result_json` — **PASS**

### 1.1 Persist-only vs runtime contract

- `slim_for_persist` runs in Worker `_seal_result_json` **after** Facade outcome is attached.  
- Kernel / Skill / Policy / in-flight Facade shape unchanged.  
- API consumers receive **persisted** (possibly truncated) JSON — same `TaskOut` fields (`summary`, `sql`, `table_preview`, `report`, `platform`, …).

### 1.2 Seal order

```478:482:backend/app/workers/analysis_worker.py
def _seal_result_json(db, task: AnalysisTask) -> None:
    """Trace columns → artifacts from full payload → P1.4 hot slim."""
    rl.apply_trace_columns(task, task.result_json)
    _materialize_artifacts(db, task)
    task.result_json = result_payload.slim_for_persist(task.result_json)
```

Matches approved: **Trace → Artifacts (full) → Slim hot**.

### 1.3 `platform.payload.omissions`

Omitting entries include `field`, `reason` (`row_cap` / `markdown_soft_cap` / `byte_budget`), and detail (`kept_rows`, `omitted_rows`, `artifact_hint`, …). `truncated: true` + limitations note when applied. `platform.execution` restored/kept on hot path.

### 1.4 Limits & tests

| Limit | Default | Coverage |
|-------|---------|----------|
| `RESULT_JSON_MAX_BYTES` | 262144 (256 KiB) | Config default; smoke forces 32 KiB and asserts size ≤ budget (+meta slack) |
| `TABLE_PREVIEW_HOT_MAX_ROWS` | 50 | Config default; smoke forces 5 and asserts `len(rows) ≤ 5` + `omitted_row_count` |

`smoke_result_payload` + Gate wiring: **PASS** at impl exit.

### 1.5 Old clients

- No removal of top-level keys required for golden-path UI.  
- Additive optional `platform.payload`.  
- Fewer preview rows / shorter markdown still parseable.  
- FE adds banner when `payload.truncated` — non-breaking.

**Note (P2, known by design):** Without object store, artifact `content_ref` resolves to **post-slim** hot fields; omissions document that — not silent full-fidelity cold retention.

---

## 2. P1.8 Token Storage ADR — **PASS**

| Check | Evidence |
|-------|----------|
| ADR-only | `docs/ADR_TOKEN_STORAGE.md` only |
| No Cookie / CSRF code | No Set-Cookie/csrf/HttpOnly in `backend/app/api` |
| TTL / revoke / localStorage acceptance | Documented in ADR tables |
| Cookie migration triggers | Three explicit conditions in ADR |

---

## 3. Release scope — **PASS**

| Check | Evidence |
|-------|----------|
| CHANGELOG / RELEASE_NOTES | Marked **Unreleased / draft**; **tag not cut** |
| No `v1.1*` tag created in this Sprint | Process: not authorized |
| No v2.0 / Phase 2 features in code | Changelog Non-goals; no HITL/Cookie/Semantic impl |

`docs/SPRINT3_FINAL_AUDIT.md` remains **independent** for a later docs-only commit (not mixed into Sprint 4 feature commit) — direction confirmed.

---

## 4. Regression — **PASS** (impl-exit evidence)

| Check | Result |
|-------|--------|
| Release Gate | PASS |
| Eval core/quality/profile | EVAL_OK |
| FE lint/build | PASS |
| Spine | Worker persist policy only; Gate/Kernel unchanged |
| Phase 2 / HITL code / Cookie MVP | Not present |

---

## 5. Residual P2 (non-blocking)

1. Smoke validates mechanism with **tightened** env (32 KiB / 5 rows), not a dedicated assert of production defaults 256 KiB / 50 in the same script (defaults still in `config.py` / `.env.example`).  
2. Artifact fidelity after slim = truncated hot target (accepted for no object store).  
3. Byte assert allows +2 KiB metadata slack.

---

## 6. Commit standard

| | |
|--|--|
| Design alignment | Met |
| Review | **PASS** |
| Suggested feature commit (when authorized) | `feat(runtime): bound hot result_json; ADR token storage; v1.1 notes draft` |
| Suggested separate docs commit | `docs(audit): add sprint3 final verification report` ← `SPRINT3_FINAL_AUDIT.md` only |
| Push / release / tag | Still **not** authorized by this review |

---

## 7. Pause

Review **PASS**. Awaiting your commit authorization (feature ± separate Sprint 3 audit docs).  
**No** push / release / v1.1 tag until separately authorized.
