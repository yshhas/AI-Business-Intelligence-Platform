# Backend (FastAPI + Worker)

Product Shell API, Redis queue consumer, and Data Plane executors.

## Run locally

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# other terminal:
python -m app.workers.analysis_worker
```

| Endpoint | Purpose |
|----------|---------|
| `GET /health/live` | Process up |
| `GET /health/ready` | DB + Redis |
| `GET /metrics` | Prometheus |
| `GET /docs` | OpenAPI |

## Quality gate

```powershell
python scripts/smoke_release_gate.py
```

Includes alembic head, Kernel/Skill/Wave3 smokes, core + quality + profile evals.

## Layout

```text
app/api/          HTTP routes (auth, datasets, tasks, mcp)
app/services/     orchestration (tasks, ACL, plane, OIDC, memory)
app/workers/      analysis_worker + agent_runtime adapter
app/models/       SQLAlchemy
alembic/          migrations
scripts/          smoke_* + release gate
```

Agent package lives at repo `../agent` — Worker calls **only** `agent.runtime.run_analysis`.

See [../docs/OPS_RUNBOOK.md](../docs/ops/OPS_RUNBOOK.md) · [../docs/API_ERROR_CODES.md](../docs/ops/API_ERROR_CODES.md).
