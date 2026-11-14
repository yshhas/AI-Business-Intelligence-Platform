# Sprint 4 Implementation Report

**Status:** Implemented · **not committed**  
**Base:** `d242bf4`  
**Scope:** P1.4 hot slim · P1.8 ADR-only · v1.1 docs drafts  

Spine unchanged.

---

## 1. Decisions delivered

| Decision | Done |
|----------|------|
| P1.4 hot slim + truncate; no object store | Yes |
| list API unchanged | Yes |
| P1.8 ADR-only (no Cookie) | Yes — `docs/ADR_TOKEN_STORAGE.md` |
| 256 KiB / preview row cap 50 | Yes (config defaults) |
| Explicit `platform.payload` omissions | Yes |
| Trace `platform.execution` kept hot | Yes |
| SPRINT3_FINAL_AUDIT separate commit | **Deferred** until commit authorization (still untracked) |

---

## 2. P1.4

| Piece | Location |
|-------|----------|
| `result_payload.slim_for_persist` | `backend/app/services/result_payload.py` |
| Worker seal | `_seal_result_json`: trace → materialize → slim |
| Config | `RESULT_JSON_MAX_BYTES`, `TABLE_PREVIEW_HOT_MAX_ROWS` |
| FE | `TaskResultPanel` truncation banner |
| Smoke | `smoke_result_payload.py` in Release Gate |

Semantics: truncated fields keep artifact `content_ref` into hot (truncated) JSON; omissions list reasons — **not silent**.

---

## 3. P1.8

`docs/ADR_TOKEN_STORAGE.md` — localStorage accepted; TTL/revoke; Cookie deferred + migration triggers.

---

## 4. v1.1 docs (draft, no tag)

- `CHANGELOG.md` — `[1.1.0] — Unreleased`  
- `RELEASE_NOTES.md` — v1.1.0 draft section  

---

## 5. Verification

| Check | Result |
|-------|--------|
| `smoke_result_payload` | **PASS** (`RESULT_PAYLOAD_SLIM_OK`) |
| frontend lint / build | **PASS** |
| Release Gate | **PASS** |
| Eval core / quality / profile | **EVAL_OK** (via Gate) |

---

## 6. Out of scope

Cookie MVP · HITL code · Phase 2 · object store · list contract change · v1.1 tag

---

## 7. Suggested commit message (when authorized)

```text
feat(runtime): bound hot result_json; ADR token storage; v1.1 notes draft
```

Separate prior commit for `docs/SPRINT3_FINAL_AUDIT.md`:

```text
docs(audit): add sprint3 final verification report
```
