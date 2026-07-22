# P0-1 Evaluation Framework — Acceptance

**Status:** ✅ **Frozen / complete** (human confirmed 2026-07-22)  
**Date:** 2026-07-22  
**Checklist:** [PHASE_P0_1_EVALUATION_CHECKLIST.md](./PHASE_P0_1_EVALUATION_CHECKLIST.md)

## Goals achieved

- [x] Repeatable Golden Eval  
- [x] Core Eval independent of live LLM → CI quality gate  
- [x] Layered metrics: Gate / Execute / Result / failure_class  
- [x] Baseline regression blocks quality rollback  
- [x] Kernel / Skill / Policy / Plane / Worker boundaries unchanged  

## Delivered

| Item | Evidence |
|------|----------|
| Golden Dataset / case format | `evals/suites/core/cases.yaml` · `evals/fixtures/file/sales_mini.csv` |
| Core deterministic runner | `evals/runner.py` · `backend/scripts/smoke_eval_golden.py` |
| Layered metrics | report `summary`: gate / execute / result / outcome / failure_class / heuristic_use |
| Baseline compare | `--fail-on-regression` · `evals/baselines/core_latest.json` |
| Release gate + CI | `smoke_release_gate.py` invokes core eval (+ baseline when present) |

## Verified locally

```text
passed=8/8 failed=0 skipped=2 (postgres_ro without DSN)
gate=1.0 execute=1.0 result=1.0 outcome=1.0
heuristic_use_count=0
EVAL_OK
```

## Architecture compliance

- [x] No Kernel / Skill Lifecycle / Worker / Policy / Data Plane boundary changes  
- [x] Deny cases do not execute  
- [x] Eval forces `allow_heuristic_sql=false`  
- [x] No RAG / ReAct / Multi-Agent / Eval UI / LLM Judge / Prompt optimizer  

## Follow-ups (recorded — **not** opened for coding)

### 1. Current Eval proves engineering-path correctness

Today’s core suite primarily validates:

- SQL Gate behavior  
- Execute path (Policy → Plane)  
- failure classification  
- regression stability  

**Later (LLM Quality phase, separate authorization):** grow coverage toward SQL accuracy, schema linking quality, harder questions, business-semantic consistency — still via golden constraints / row checks, **not** by turning Eval into a product.

### 2. Standing principles

- Eval = **quality proof**, not an Eval platform  
- Do **not** introduce LLM Judge / auto Prompt optimization / labeling systems in this arc  
- Do **not** reshape Agent architecture because of Eval  

Deferred (not Won't Do forever): Auto Prompt optimization · LLM Judge · 人工标注 · Eval Web UI · 数据集管理 · 模型排行榜  

## Operator commands

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\smoke_eval_golden.py --suite core
.\.venv\Scripts\python.exe scripts\smoke_eval_golden.py --suite core `
  --fail-on-regression ..\evals\baselines\core_latest.json
```

**Next:** [PHASE_P0_2_COST_BUDGET_CHECKLIST.md](./PHASE_P0_2_COST_BUDGET_CHECKLIST.md) (design only until confirmed).
