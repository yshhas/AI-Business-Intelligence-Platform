# Phase M6 — Artifact Lifecycle Checklist

**Status:** ✅ Implemented & **frozen** — see [PHASE_M6_ACCEPTANCE.md](PHASE_M6_ACCEPTANCE.md) · [PHASE_M6_RETROSPECTIVE.md](PHASE_M6_RETROSPECTIVE.md)  
**Era:** 2 — Enterprise Capability Enhancement  
**Prerequisite:** M4 Trace + M5 Permission **frozen**  
**Theme:** Artifact as platform-managed output — not BI/CMS product  

## Confirmed decisions

| # | Decision |
|---|----------|
| 1 Persistence | Thin table `run_artifacts` (metadata + content_ref) |
| 2 ID | UUID |
| 3 Global API | Out — run-scoped only |
| 4 Retention | Omit — only `available` \| `unavailable` |
| 5 Table payload | content_ref only (no copy) |
| 6 Partial | Record `unavailable` stubs |

## Goal

```text
Agent Run
    ↓
Execution Trace
    ↓
Artifact
    ↓
Lineage / Access
```

> Artifact 从 `result_json` 附属投影，升级为 **可标识、可列举、可追溯到 Run、受同一权限模型约束** 的平台产物——不做 Report Center / CMS / PDF 工厂。

## Hard stop-lines

- No Report Center / Artifact CMS / collaborative editing  
- No PDF/export farm / new chart types as phase goal  
- No standalone Artifact microservice  
- No Kernel rewrite; reuse `Artifact` + `to_execution_trace` ArtifactRef  
- No IAM expansion beyond M5 matrix  
- Keep legacy `result_json` projection for UI compatibility  

## Architecture

```text
Skill → RunResult.artifacts[] (UUID)
        ↓
Facade to_legacy_result_json + to_execution_trace (ArtifactRef)
        ↓
Worker: result_json + run_artifacts (metadata + content_ref)
        ↓
API: GET /tasks/{id}/artifacts[/{artifact_id}]
        ↓
Access: M5 artifact.list / artifact.get (= run visibility)
```

## APIs

| API | Role |
|-----|------|
| `GET /tasks/{id}` | Legacy result_json (unchanged) |
| `GET /tasks/{id}/execution` | Trace; ArtifactRefs match durable ids |
| `GET /tasks/{id}/artifacts` | List metadata (+ lineage) |
| `GET /tasks/{id}/artifacts/{artifact_id}` | Metadata + payload via content_ref |

**Out:** `GET /artifacts/{id}`

## Acceptance

See [PHASE_M6_ACCEPTANCE.md](PHASE_M6_ACCEPTANCE.md).

## One-line summary

> M6 makes **Artifacts** first-class platform outputs with identity and Run/Trace lineage — queryable and permissioned like Runs — without becoming a reporting CMS.
