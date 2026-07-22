# Observation Log — Hold Window（历史）

**Status:** ⏹ **Superseded** — closed by **Release v1.0 Feature Freeze** (2026-07-22)  
**Current authority:** [`FINAL_RELEASE.md`](./FINAL_RELEASE.md) · [`project_upgrade_plan.md`](../project_upgrade_plan.md)  
**Opened:** 2026-07-22 · **Closed:** 2026-07-22 (post Wave 0–3 + Stabilization)

> 本文件保留作审计轨迹。新的观察/变更请先更新 FINAL_RELEASE / plan；无明确需求不编码。

---

## Phase confirmation (2026-07-22)

| Theme | Observe posture | Explicitly not doing |
|-------|-----------------|----------------------|
| **E1 Linking** | Track vs **quality baseline** only | No proactive linker/Prompt “optimization” |
| **E2 Explainability** | Real-use value on Analyze | No Trace Explorer / Observability product |
| **Cost** | Log real constraint demand only | No Cost UI / FinOps system early |
| **SQL Quality** | Collect failure clusters only | No Repair until evidence + authorize |

### Decision principle (unchanged)

```text
稳定数据 → 提交设计
明确痛点 → 授权切片
无证据   → 不开发
```

### Frozen (no start)

SQL Repair · Connector · Cost UI · Eval 平台化 · New Skill · RAG / ReAct / Multi-Agent

### If a Go condition triggers

Before any checklist or code, submit:

1. 现象与数据证据（rows in this log + suite/Run refs）  
2. 目标收益  
3. 影响范围  
4. 是否改变现有架构边界（Skill → Policy → Plane → Trace）

Then fill retrospective §5 authorize template. **No implementation without that packet.**

---

## How to use

1. After Demo / Eval / ops sessions, append a dated row under the relevant theme (do not invent metrics).  
2. Prefer facts: suite JSON paths, Run ids, `failure_class`, first failing `node_name`, screenshots notes.  
3. When a theme meets **Go**, fill the authorize template in the retrospective §5 — then write a thin checklist. Until then: **Hold**.

**Baseline snapshot (freeze day — quality suite):**

| Metric | `evals/baselines/quality_latest.json` |
|--------|----------------------------------------|
| `link_ok_rate` | 0.5 |
| `link_fallback_rate` | 0.1667 |
| `link_failed_rate` | 0.1667 |
| `link_status_distribution` | ok:3 · partial:1 · fallback_full:1 · failed:1 |
| `heuristic_use_count` | 0 |

Re-run: `backend` → `python scripts/smoke_eval_golden.py --suite quality`

---

## 1. E1 Linking

### Watch

| Signal | Source |
|--------|--------|
| `link_ok_rate` | quality report `summary.link_ok_rate` |
| `link_fallback_rate` / `link_failed_rate` | same |
| `fallback_full` reason distribution | Trace `sql_quality.link_reason` · step `link_schema` · case ids |
| SQL fail vs linking correlation | First failing step: `link_schema` vs `generate_sql` / `validate_sql` / `execute_sql` |

### Log

| Date | link_ok_rate | fallback_full reasons (counts) | Fail stage mix (link / gen / gate / exec) | Notes | Observer |
|------|--------------|--------------------------------|---------------------------------------------|-------|----------|
| 2026-07-22 | 0.5 (baseline) | suite fixture: `no_token_overlap`×1 (synthetic) | n/a — observation phase open | Baseline only; no linker tuning | — |
| | | | | | |

### Interpreting toward Go/No-go

- Rising `fallback_full` on **wide real schemas** → design note first (still not Repair).  
- Failures clustered **after** `link_status=ok|partial` → candidate **C3 Repair** evidence packet.  
- Failures clustered on linking / empty overlap → **do not** open Repair.

---

## 2. E2 Explainability

### Watch

| Signal | How |
|--------|-----|
| Can user locate problem via Analyze Trace? | Demo: deny / fallback / fail Run — without opening raw JSON |
| Still-missing info | Note gaps (budget gauge, retry history, column glossary, etc.) |

### Log

| Date | Scenario (deny / fallback / fail / success) | Located without raw JSON? (Y/N) | Missing info noted | Notes | Observer |
|------|-----------------------------------------------|----------------------------------|--------------------|-------|----------|
| 2026-07-22 | — | — | Observation phase open; E2 frozen | No Trace product expansion | — |
| | | | | | |

### Interpreting

- Persistent gaps that are **budget used/cap** → feed **C2** evidence, not E2 reopen.  
- Requests for Trace Explorer / LangSmith → **Won't Do**.

---

## 3. Cost

### Watch

| Signal | Source |
|--------|--------|
| Real constraint demand | `budget_rejected` / HTTP 429 counts when budget > 0 |
| Token visibility enough? | Task `llm_total_tokens` + E2 Resources vs “need used/budget UI” |

### Log

| Date | Budget enabled? (Y/N · value) | budget_rejected / 429 seen? | Users confused without Cost UI? (Y/N) | Notes | Observer |
|------|-------------------------------|-----------------------------|----------------------------------------|-------|----------|
| 2026-07-22 | Default often 0 (off) | — | — | Record demand only; no Cost system | — |
| | | | | | |

### Go toward C2 only with evidence packet (retrospective §4.2).

---

## 4. SQL Quality (Repair evidence)

### Watch

| Signal | Source |
|--------|--------|
| Stable, classifiable failure clusters | Sample Runs: Gate reason / execute error patterns |
| Worth Repair? | Closed enum would cover majority; linking not dominant miss |

### Log

| Date | Sample n | Cluster labels (draft) | % post-link (gate/exec) | % linking-dominated | Repair worth? (Y/N/?) | Notes | Observer |
|------|----------|------------------------|-------------------------|---------------------|------------------------|-------|----------|
| 2026-07-22 | 0 | — | — | — | ? | Collect clusters only; no Repair | — |
| | | | | | | | |

### Go toward C3 only with evidence packet (retrospective §4.2).

---

## 5. Standing freeze (do not start)

| Item | Status |
|------|--------|
| SQL Repair | Frozen — evidence + authorize |
| Connector | Frozen — named source + charter |
| Cost UI | Frozen — demand evidence |
| Eval 平台化 | Won't Do this arc |
| New Skill | Frozen — no charter |
| RAG / ReAct / Multi-Agent | Won't Do |

**RepoPilot boundary:** unchanged.

---

## 6. Exit observation

When ready to leave Hold, complete:

```text
Date:
Evidence: (rows above + refs)
1. 现象与数据证据:
2. 目标收益:
3. 影响范围:
4. 是否改变架构边界: no | yes (explain)
Candidate: Hold | C1 | C2 | C3 | C4
Authorize template (retrospective §5): filled yes/no
```

Until that packet exists: **no implementation checklist, no coding.**
