# Sprint 3 Implementation Report

**Status:** Implemented · Gate/Eval/FE **PASS** · **not committed**  
**Base:** `e937f0a`  
**Authorized scope:** P1.10 · P1.7 · HITL Design-only  

Spine unchanged: Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts.

---

## 1. Decisions locked

| Decision | Delivered |
|----------|-----------|
| Dataset `/preview` + Run `table_preview` same redaction helpers | Yes |
| mysql-ro **disabled** UI placeholder (no fake bind) | Yes |
| OIDC login button deferred | Yes (not added) |
| ACL UI edits `tables_json` via existing PUT contract | Yes |
| HITL = `docs/HITL_SQL_APPROVAL_DESIGN.md` only | Yes |

---

## 2. P1.7 Guardrails

| Piece | Change |
|-------|--------|
| `agent/guardrails.py` | `redact_table_preview` / `redact_preview_payload`; Facade covers `table_preview` |
| `dataset_service.preview_dataset` | Applies `redact_preview_payload` before return |
| Smoke | `GUARDRAILS_TABLE_PREVIEW_OK` in `smoke_wave3_platform` |

Not Policy Gate. Heuristic string redaction only.

---

## 3. P1.10 Product Shell Visibility

| Piece | Change |
|-------|--------|
| Analyze Skill picker | `data.bi` / `data.profile`; `createTask` sends `skill_id` |
| Datasets mysql-ro | Disabled card + explanation; **no** API call |
| Datasets ACL | Owner panel: load/save/clear; `user_id` + read/run + tables CSV → `tables` / `tables_json` |
| `docs/demo.md` | Skill / ACL / mysql notes |
| OIDC UI | Not added |

---

## 4. HITL Design-only

`docs/HITL_SQL_APPROVAL_DESIGN.md` — states/API/UX sketch; **Non-goal for v1.1 code**; no Worker lifecycle changes.

Also present (design phase, untracked until commit): `docs/SPRINT3_DESIGN_REVIEW.md`.

---

## 5. Verification

| Check | Result |
|-------|--------|
| frontend `lint` | **PASS** |
| frontend `build` | **PASS** |
| `smoke_wave3_platform` | **PASS** (`GUARDRAILS_TABLE_PREVIEW_OK`) |
| `smoke_data_profile` | **PASS** |
| `smoke_release_gate` | **PASS** |
| Eval core / quality / profile | **EVAL_OK** |

---

## 6. Out of scope (confirmed)

HITL implementation · Worker Run states · P1.4 · P1.8 · Semantic · Multi-Agent · IaC/K8s · OIDC login button · mysql-ro FE bind call

---

## 7. Follow-ups (not this Sprint)

- Workspace members list API for nicer ACL picker  
- Enable mysql-ro UI when product-ready  
- HITL implementation (Phase 2+)  

---

## 8. Commit readiness

Implementation complete vs approved design. **Await Implementation Review** before commit.

Suggested message (when authorized):

```text
feat(shell): skill picker, ACL UI, preview guardrails; HITL design-only
```

**Not done:** commit · push · release.
