# Ops — Configuration Matrix

**Status:** Era 3 Deployment Hygiene (DH.1)  
**Secrets:** never put real passwords in docs or committed `.env` — use [`.env.example`](../.env.example).

| Variable | Default | Required | Used by | Notes |
|----------|---------|----------|---------|-------|
| `DATABASE_URL` | (see example) | **API · Worker** | Platform metadata Postgres | Host **5433** · Compose api/worker → `@postgres:5432` |
| `REDIS_URL` | `redis://localhost:6379/0` | **API · Worker** | Queue + ready probe | Compose → `redis:6379` |
| `JWT_SECRET` | change-me… | **API** | Auth | **production/staging:** random ≥32 chars, not a known placeholder |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | API | Access JWT TTL | P0 short-lived |
| `REFRESH_TOKEN_EXPIRE_MINUTES` | `10080` | API | Refresh JWT TTL | `POST /api/v1/auth/refresh` |
| `CORS_ORIGINS` | localhost:5173… | API | Comma-separated | Configurable CORS |
| `RATE_LIMIT_ENABLED` | `true` | API | Redis rate limits | Auth + task create |
| `RATE_LIMIT_AUTH_PER_MINUTE` | `30` | API | Login/register | Per IP+email |
| `RATE_LIMIT_TASK_CREATE_PER_MINUTE` | `60` | API | Analyze enqueue | Per user+workspace |
| `WORKER_HEALTH_HOST` / `WORKER_HEALTH_PORT` | `0.0.0.0` / `8001` | Worker | P1 HTTP probe | `0` port disables; Compose maps `8001` |
| `METRICS_ENABLED` | `true` | API | `GET /metrics` | Prometheus text |
| `APP_NAME` / `APP_ENV` | BI / development | API | Health payload | |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | API process | Bind | |
| `LOG_FORMAT` | `text` | API · Worker | `text` \| `json` | T-08 structured logs |
| `LOG_LEVEL` | `INFO` | API · Worker | | |
| `SKILL_DATA_BI_ENABLED` | `true` | API · Worker | T-09 enqueue/dispatch gate | `false` → 403 on create |
| `SKILL_DATA_BI_VERSION` | `1.0.0` | API · Worker | Pinned on Run/Trace | |
| `SKILL_DATA_PROFILE_ENABLED` | `true` | API · Worker | Wave 3 second Skill | |
| `SKILL_DATA_PROFILE_VERSION` | `1.0.0` | API · Worker | Pinned on Run/Trace | |
| `MYSQL_RO_DSN` | empty | API · Worker | Optional `mysql_ro` plane | `mysql://user:pass@host:3306/db` |
| `WORKSPACE_MEMORY_ENABLED` | `true` | Worker | Persist linking synonyms | |
| `WORKSPACE_MEMORY_TTL_DAYS` | `90` | Worker / API | Synonym row TTL (0 = no expiry on write) | P1.3 |
| `WORKSPACE_MEMORY_MAX_ROWS` | `2000` | Worker / API | Max rows per workspace (expire then LRU) | P1.3 |
| `RESULT_JSON_MAX_BYTES` | `262144` | Worker | Hot result_json UTF-8 budget after artifact materialize | P1.4 |
| `TABLE_PREVIEW_HOT_MAX_ROWS` | `50` | Worker | Max rows kept in hot table_preview | P1.4 |
| `OIDC_ENABLED` | `false` | API | SSO MVP | Requires issuer/client/redirect |
| `OIDC_ISSUER` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` / `OIDC_REDIRECT_URI` | empty | API | OIDC | Endpoints must share issuer host |
| `OIDC_SCOPES` | `openid email profile` | API | OIDC | |
| `TASK_SSE_POLL_SECONDS` | `0.5` | API | T-10 SSE DB poll interval | Progress only |
| `TASK_SSE_HEARTBEAT_SECONDS` | `5` | API | T-10 SSE heartbeat | |
| `TASK_SSE_MAX_SECONDS` | `600` | API | T-10 SSE max watch | Client may fall back to poll |
| `UPLOAD_DIR` / `DUCKDB_DIR` | `./data/...` | API · Worker | File plane | Relative to repo root |
| `MAX_UPLOAD_BYTES` | `20971520` | API | Upload cap | |
| `ANALYSIS_RUNTIME` | `mock` (code) / `agent` (`.env.example` & Compose) | **Worker** | `mock` \| `agent` | **production/staging:** must be `agent` (boot refuses `mock`) |
| `ANALYSIS_QUEUE_KEY` | `aibi:analysis_tasks` | API · Worker | Redis List key | |
| `REDIS_BRPOP_TIMEOUT_SECONDS` | `5` | Worker | Idle reclaim window | |
| `SQL_DEFAULT_LIMIT` | `200` | Worker (agent) | Select limit | |
| `SQL_MAX_RETRIES` | `2` | Worker (agent) | Skill retries (graph) | Not E3 auto-retry |
| `LLM_API_KEY` | empty | Worker (agent) · optional evals `llm` suite | Optional | Empty → heuristic if allowed; **Eval core forces heuristic off** |
| `LLM_PROVIDER` | `openai_compatible` | Worker (agent) | `openai_compatible` \| `anthropic` \| `gemini` | Default base_url/model when those are empty-ish; HTTP path stays OpenAI-compatible |
| `LLM_BASE_URL` / `LLM_MODEL` | DeepSeek defaults | Worker | | Override per provider or gateway |
| `LLM_MAX_RETRIES` | `2` | Worker (agent) | HTTP retries after 1st attempt | timeout/transport/429/5xx only |
| `LLM_RETRY_BACKOFF_SECONDS` | `0.5` | Worker (agent) | Retry base delay | Exponential + jitter |
| `LLM_RETRY_BACKOFF_MAX_SECONDS` | `8.0` | Worker (agent) | Cap on backoff | |
| `ALLOW_HEURISTIC_SQL` | `true` | Worker | Dev golden path | **Forced `false` when `APP_ENV` is production/staging** |
| `LLM_TOKEN_BUDGET_PER_WORKSPACE_DAY` | `0` | API (enqueue) | P0-2 soft budget | `0`=off; UTC day; 429 + `budget_rejected`; does not kill in-flight |
| `RUN_TIMEOUT_SECONDS` | `120` | API · Worker | Per-Run wall clock | |
| `RUN_MAX_IN_FLIGHT` | `4` | API · Worker | E3 global running cap | Enqueue 429 when full |
| `ANALYSIS_QUEUE_MAX_DEPTH` | `50` | API | E3 queue `LLEN` cap | Enqueue 429 when full |
| `STALE_RUNNING_SECONDS` | `0` (= timeout+60) | Worker | E3 reclaim TTL | |
| `RUN_HEARTBEAT_INTERVAL_SECONDS` | `15` | Worker | Stale freshness only | `0` = disable updates |
| `POSTGRES_RO_DSN` | empty | Worker (agent) + M3 smoke + eval postgres_ro cases | RO data plane | Host **5434** · Compose → `@postgres_ro:5432`; empty → skip M3 / eval RO cases |
| Eval (P0-1) | — | CI via `smoke_eval_golden --suite core` | `evals/suites/**` | Baseline `evals/baselines/core_latest.json`; wired in release gate |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Frontend | | |

### Compose-only (not app Settings)

| Variable | Role |
|----------|------|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Platform Postgres container |
| T-12 `api` / `worker` | Image `aibi-app:local`; env overrides DB/Redis/RO DNS |

### Role checklist

| Role | Must have |
|------|-----------|
| **API** | `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET` |
| **Worker** | Same DB/Redis + `ANALYSIS_RUNTIME`; E3 caps optional (defaults apply) |
| **Analyze golden path** | Worker running + ready datasets |
| **postgres_ro Demo** | `POSTGRES_RO_DSN` + Compose `postgres_ro` |

See [OPS_RUNBOOK.md](./OPS_RUNBOOK.md) for bring-up order.
