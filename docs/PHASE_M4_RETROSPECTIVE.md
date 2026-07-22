# Phase M4 — Freeze + Retrospective

**Status:** ✅ **Formally closed / frozen** (2026-07-22)

## Narrative completed

```text
Foundation M1–M3: Skill · Policy · Run · Data Plane
M4: Execution Trace Model
    ToolCall · PolicyDecision · ArtifactRef · queryable Run Trace
```

**Proof (not an Audit product):**
> Run 从“执行记录”升级为可查询的 Execution Trace，能回答做了什么 / 调了哪些工具 / Policy 为何允许拒绝 / 产出了哪些 Artifact。

## Freeze (do not expand now)

| Keep | Do not |
|------|--------|
| `platform.execution` as Trace source of truth | events 表 / event sourcing |
| JSON snapshot + `skill_id` / `source_type` / `policy_denied` | Audit Center / SIEM / 独立审计服务 |
| `GET /tasks/{id}/execution` + list filters | 日志平台 / 跨 workspace 合规套件 |
| Run-adjacent Trace UI | 把 Observability 下沉进 Kernel |

M1–M3 Foundation boundaries remain frozen. Next: **M5 thin Resource Permission** (design → then code).

---

## Retrospective

### 1. Is `platform.execution` enough as Trace v1?

**Verdict: Yes.**

| Strength | Why |
|----------|-----|
| Correlated ids | `call_id` / `decision_id` / `artifact_id` + optional `step_no` |
| Deny reasons | Policy `ok=false` + `reason` persisted |
| Query | Denormalized filters without audit warehouse |
| Partial runs | `AgentAnalysisError` + `summary.incomplete` |

| Gap (acceptable) | Note |
|------------------|------|
| Cancel/timeout mid-flight may lack ToolCalls | Cooperative limit; best-effort only |
| Steps still graph-centric | Timeline appendix; Trace is enterprise model |
| No skill_version | Deferred to Skill lifecycle |

### 2. Did we avoid Audit productization?

**Verdict: Yes** — Trace is a Run document + filters + panel, not a new product surface.

### 3. What unlocks M5?

Traces make authorization Demoable: deny bind/run/view should be explainable alongside Policy deny in the same governance story.

```text
Agent Run → Execution Trace → Authorized Resource Access (M5)
```
