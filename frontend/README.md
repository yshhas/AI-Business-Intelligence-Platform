# Frontend (React + TypeScript)

Product shell for the Enterprise Data Agent Platform: auth, workspaces, datasets, Analyze, Tasks, Execution Trace, and Artifacts.

## Run

```powershell
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173 — Vite proxies `/api` and `/health` to the API on `:8000`.

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Local Vite dev server |
| `npm run build` | `tsc -b` + production bundle |
| `npm run lint` | oxlint |
| `npm run preview` | Preview production build |

## Routes

| Path | Notes |
|------|-------|
| `/` | Home + health probe |
| `/login`, `/register` | JWT auth (access + refresh) |
| `/app` | Dashboard (auth required) |
| `/app/datasets` | Upload / Postgres RO bind / ACL (MySQL RO & MCP are API-only MVP) |
| `/app/analyze` | Create analysis tasks + SSE progress (`data.bi` UI; `data.profile` via API `skill_id`) |
| `/app/tasks` | Task history, Trace, Artifacts |

## Auth notes

- Access token (short TTL) + refresh token stored in `localStorage` (Cookie migration is a later decision).
- API client refreshes once on `401` before clearing the session.
- Optional OIDC is API-only (`/api/v1/auth/oidc/*`); no SSO button in UI yet.

Backend must be running (`uvicorn` or Compose `api`) for authenticated flows.

TanStack Query is used on Dashboard / Datasets / Tasks list pages; Analyze still uses targeted `useEffect` + SSE for Run progress.
