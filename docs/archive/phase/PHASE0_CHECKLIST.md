# Phase 0 execution checklist

Operational order for scaffolding. Scope freeze: **no** LangGraph, tasks, reports, datasets.

| Step | Goal | Create / modify | Acceptance | Core knowledge |
|------|------|-----------------|------------|----------------|
| 0.1 | Monorepo layout | `README.md`, `.gitignore`, `.env.example`, `frontend/`, `backend/`, `agent/`, `database/`, `docker/`, `docs/` | Directories exist; README states MVP vs RepoPilot | Boundary: who depends on whom |
| 0.2 | Infra Compose | `docker/docker-compose.yml`, `docker/README.md` | `docker compose up -d`; Postgres healthy; Redis up (unused) | Volumes, healthchecks, connection URLs |
| 0.3 | API health | `backend/app/main.py`, `core/config.py`, `api/routes_health.py`, `requirements.txt` | `GET /health` → `status=ok` | FastAPI app factory, Settings, CORS |
| 0.4 | Web shell | `frontend/` Vite React TS, routes, layout, health probe | `npm run dev` opens shell; can see API health | SPA routing, proxy vs CORS |
| 0.5 | Docs + agent stub | `agent/README.md`, `docs/PHASES.md`, `docs/demo.md` | Agent has no graph code; phase checklist present | Why agent is deferred |

**Stop line:** do not add auth tables, upload, Redis consumers, or LangGraph in Phase 0.
