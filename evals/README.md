# Evaluation Framework (P0-1)

Deterministic golden suites for Text-to-SQL / Gate / Data Plane regression.
**Not** an Eval product platform (no UI, labeling, LLM-judge, auto-prompt).

## Layout

```text
evals/
  fixtures/file/sales_mini.csv
  suites/core/cases.yaml     # CI / release gate
  suites/quality/cases.yaml  # E1-C Schema Linking (CI / release gate)
  suites/llm/cases.yaml      # optional live LLM
  baselines/core_latest.json
  baselines/quality_latest.json
  reports/                   # local last-run artifacts (optional)
  runner.py                  # library used by smoke_eval_golden.py
```

## Run

```powershell
cd backend
pip install -r requirements.txt   # includes PyYAML
.\.venv\Scripts\python.exe scripts\smoke_eval_golden.py --suite core
.\.venv\Scripts\python.exe scripts\smoke_eval_golden.py --suite quality `
  --fail-on-regression ..\evals\baselines\quality_latest.json
.\.venv\Scripts\python.exe scripts\smoke_eval_golden.py --suite core `
  --fail-on-regression ..\evals\baselines\core_latest.json
```

Optional LLM suite (skipped if `LLM_API_KEY` empty):

```powershell
.\.venv\Scripts\python.exe scripts\smoke_eval_golden.py --suite llm
```

## Case modes

| Mode | Purpose |
|------|---------|
| `sql_inject` | Fixed SQL → Policy Gate → optional Execute |
| `fixture_meta` | Fixture load / schema sanity |
| `link_only` | Schema Linking Lite only (no LLM) |
| `pipeline` | Full `run_analysis` (heuristic **forced off**) |

## Metrics

Report `summary` includes:

- `gate_pass_rate`
- `execute_success_rate`
- `result_match_rate`
- `outcome_success_rate`
- `failure_class_distribution`
- `heuristic_use_count` (must be 0)
- `link_status_distribution` / `link_ok_rate` / `link_fallback_rate` / `link_failed_rate`
- `schema_link_cases` / `schema_link_passed`

## Prompt change gate

See [`docs/PROMPT_CHANGE_GATE.md`](../docs/design/PROMPT_CHANGE_GATE.md).  
Bump `PROMPT_SQL_VERSION` in `agent/prompts_sql.py` when prompts change, then re-run core + quality suites.

## Updating the baseline

After an **intentional** quality win (and core is green):

```powershell
.\.venv\Scripts\python.exe scripts\smoke_eval_golden.py --suite core `
  --report ..\evals\baselines\core_latest.json
```

Commit the new baseline only when rates/cases should become the new floor.

## Architecture rules

- Calls `agent.runtime.run_analysis` / `apply_sql_select_gate` only
- Does **not** edit Kernel, Worker, Lifecycle, or Policy boundaries
- Deny cases must not execute on the Data Plane
