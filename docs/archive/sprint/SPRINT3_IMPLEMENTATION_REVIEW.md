# Sprint 3 Implementation Review Report

**Review date:** 2026-07-22  
**Base:** `e937f0a` · Sprint 3 changes **uncommitted**  
**Scope:** P1.7 · P1.10 · HITL Design-only  
**Verdict:** **PASS** — suitable for commit after authorization  

**Not performed:** commit · push · release · code fixes

---

## Executive verdict

| Area | Result | Blocking? |
|------|--------|-----------|
| P1.7 Guardrails | Same helpers; Facade for Run; Shell preview uses shared redact | No |
| P1.10 Product Shell | Existing APIs only; mysql disabled honest; ACL contract OK | No |
| HITL Design-only | Docs only; no Run status / Worker code | No |
| Gate / Eval / FE | Reported PASS | No |
| Scope creep (P1.4/1.8/Phase 2) | None found | No |
| Spine drift | None | No |

**P0:** none  
**P1:** none  
**P2:** residual notes below  

---

## 1. P1.7 Guardrails — **PASS**

### 1.1 Same redaction boundary

| Path | Mechanism |
|------|-----------|
| Run `result_json.table_preview` | `apply_output_guardrails` → `redact_table_preview` |
| Dataset HTTP `/preview` | `_apply_preview_guardrails` → `redact_preview_payload` → **same** `redact_table_preview` / `redact_text` |

Approved intent met: **one heuristic family**, not Policy. Dataset preview is applied in Product Shell service after plane read (not via Facade), which matches the signed decision (“同期脱敏 / 同一 helpers”), not a second Policy layer.

### 1.2 Still on Facade output for Runs

`agent/runtime.py` still calls `apply_output_guardrails(legacy)` after Kernel/Skill projection — post-Facade, pre-Worker persist of outcome payload.

### 1.3 Not Policy Gate / SQL semantics

- No changes to Gate validators or execute path found in this Sprint.  
- Redaction is **string-only** on display fields/cells; numeric/boolean untouched.  
- SQL text generation/execution unchanged.

Smoke: `GUARDRAILS_TABLE_PREVIEW_OK` asserted.

---

## 2. P1.10 Product Shell — **PASS**

### 2.1 Skill picker

- FE sends optional `skill_id` already supported by `TaskCreateRequest`.  
- No new backend skill registry or Kernel contract.  
- Values limited to `data.bi` | `data.profile` in UI.

### 2.2 mysql-ro disabled

- Card + disabled button + explicit copy that API exists but shell does **not** call it.  
- `datasets.ts` has **no** `bindMysqlRo` / `mysql-ro` client.  
- Does not fake success.

### 2.3 ACL UI / `tables_json`

- Uses existing `GET/PUT .../datasets/{id}/acl`.  
- Grant body: `user_id`, `can_read`, `can_run`, `tables` → maps to service `tables_json`.  
- Empty PUT clears ACL → default open (existing semantics).  
- Owner-only UI gate (`role === 'owner'`) aligns with `DATASET_ACL_*` owner requirement.  
- No new permission model / no Policy Gate rewrite.

---

## 3. HITL Design-only — **PASS**

| Check | Evidence |
|-------|----------|
| Design doc only | `docs/HITL_SQL_APPROVAL_DESIGN.md` |
| No `awaiting_approval` in backend app code | Grep empty |
| No approve/reject routes | None |
| Worker / Skill lifecycle | Untouched for HITL |
| Explicit Non-goal for v1.1 code | Document §8 |

---

## 4. Regression & boundaries — **PASS**

| Check | Result |
|-------|--------|
| frontend lint/build | PASS (implementation exit) |
| Release Gate | PASS |
| Eval core/quality/profile | EVAL_OK |
| P1.4 / P1.8 / Semantic / Multi-Agent | Not introduced |
| Spine | UI→Shell HTTP; guardrails post-output; Policy untouched |

---

## 5. Residual notes (P2 — non-blocking)

1. **No dedicated HTTP smoke** that hits Dataset `/preview` and asserts redaction (logic covered via shared helper + Facade smoke). Optional follow-up.  
2. **ACL UX:** manual `user_id` UUID (no members list API) — accepted MVP; document in demo.  
3. **Preview guardrails fail-open** on import error (`_apply_preview_guardrails` except → raw data) — intentional availability bias; low risk.  
4. Column **name** redaction could rename rare email-like headers in UI — heuristic only.

---

## 6. Commit standard

| | |
|--|--|
| Design alignment | Met |
| Review | **PASS** |
| Commit / push / release | **Awaiting your authorization** |

Suggested message (when authorized):

```text
feat(shell): skill picker, ACL UI, preview guardrails; HITL design-only
```

Include untracked/modified Sprint 3 files + design/report docs as appropriate; exclude secrets/runtime artifacts.

---

## 7. Pause

Review **PASS**. No code changes made in this review turn.  
Waiting for **commit authorization** (push/release still out of scope until separately allowed).
