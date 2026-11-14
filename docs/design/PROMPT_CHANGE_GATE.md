# Prompt Change Gate

**Status:** P0 Trust (Wave 1.1)  
**Goal:** Prompt / few-shot / injection-boundary edits must be falsifiable before merge.

## Version pin

`agent/prompts_sql.py` exports:

```python
PROMPT_SQL_VERSION = "sql-v1.0.0"
```

**Rule:** Any change to Text-to-SQL system/user prompt construction bumps this string (semver-like suffix is enough).

## Mandatory checks (local or CI)

```powershell
cd backend
python scripts/smoke_sql_prompt.py
python scripts/smoke_eval_golden.py --suite core --report ../evals/reports/core_gate.json
python scripts/smoke_eval_golden.py --suite quality --report ../evals/reports/quality_gate.json
```

Release gate already runs core + quality suites (heuristic forced off).

## Optional live LLM

```powershell
python scripts/smoke_eval_golden.py --suite llm
```

Skipped cleanly when `LLM_API_KEY` is empty — never required for merge.

## Do not

- Land prompt edits without bumping `PROMPT_SQL_VERSION`
- Re-enable heuristic SQL inside eval suites
- Skip baseline regression compare when updating known-good baselines intentionally (update `evals/baselines/*` in the same PR)
