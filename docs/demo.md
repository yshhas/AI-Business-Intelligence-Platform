# Demo script — Enterprise Data Agent Platform

**Status:** **Release v1.0 Feature Freeze**  
**Stack:** Compose (Postgres + Redis + postgres_ro + API + Worker) · host frontend optional  
**Full narrative:** [FINAL_RELEASE.md](./FINAL_RELEASE.md)

## Bring-up

```powershell
copy .env.example .env
# Set a non-default JWT_SECRET for any shared environment
docker compose -f docker/docker-compose.yml --env-file .env up -d --build
# Ready: http://127.0.0.1:8000/health/ready
```

Frontend (host):

```powershell
cd frontend
npm install
npm run dev
```

## Golden path A — file plane (DuckDB)

1. Register / login at http://127.0.0.1:5173  
2. **Datasets** → upload a CSV with `region` / `product` / `amount` (or `evals/fixtures/file/sales_mini.csv`)  
3. **Analyze** → pick Skill (`data.bi` or `data.profile`) → question: `按区域汇总销售额并排序` (or English equivalent)  
4. Wait for SSE progress → task **succeeded**  
5. Confirm UI shows: SQL · table preview · chart · report · Execution Trace · Artifacts  
6. Steps should include `link_schema`, `generate_sql`, `validate_sql`, `execute_sql`, `build_charts`, `write_report`  
7. Owner (optional): Datasets → ACL panel — empty ACL = default open; grants use member `user_id` UUID  
8. MySQL RO card is a **disabled placeholder** (API exists; UI does not call it)

## Golden path B — Postgres RO plane

1. Ensure `POSTGRES_RO_DSN` is set and Compose `postgres_ro` is up  
2. **Datasets** → Bind Postgres readonly (demo allowlisted `public.*` tables)  
3. Analyze a question against the RO dataset  
4. Illegal SQL / non-allowlist → `failure_class=policy_denied`

## Golden path C — second Skill

**UI:** Analyze → Skill = `data.profile` → submit.

**API:**

```http
POST /api/v1/workspaces/{id}/tasks
{ "dataset_id": "...", "question": "profile this dataset", "skill_id": "data.profile" }
```

Same Worker / Kernel / Gate / Trace path as `data.bi`.

## Governance demos

| Demo | Expect |
|------|--------|
| Cancel a running task | `cancelled` + incomplete Trace summary |
| Soft token budget exceeded | HTTP 429 · `budget_rejected` (no Redis enqueue) |
| Queue / in-flight full | HTTP 429 · `capacity_rejected` |
| Auth rate limit (rapid login) | HTTP 429 · rate limit detail |

## Regression

```powershell
cd backend
python scripts/smoke_release_gate.py
```

AI quality (heuristic forced off in suites):

```powershell
python scripts/smoke_eval_golden.py --suite core
python scripts/smoke_eval_golden.py --suite quality
```

See [OPS_RUNBOOK.md](./OPS_RUNBOOK.md) and [API_ERROR_CODES.md](./API_ERROR_CODES.md).
