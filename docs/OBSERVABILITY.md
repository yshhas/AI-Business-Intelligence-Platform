# Observability

**Status:** Wave 2 thin stack

## Metrics endpoint

When `METRICS_ENABLED=true` (default), the API exposes Prometheus text at:

```
GET /metrics
```

Counters/gauges include enqueue totals, terminal task counts, and queue depth
(see `backend/app/core/metrics.py`).

## Worker health

The Worker runs a lightweight HTTP server (default **`:8001`**) for probes:

| Path | Purpose |
|------|---------|
| `/health/live` | Process alive |
| `/health/ready` | Worker ready (queue consumer) |

Compose maps host `8001:8001`. Set `WORKER_HEALTH_PORT=0` to disable.

## Docker Compose — optional `obs` profile

Enable Prometheus + Grafana without affecting the default stack:

```powershell
docker compose -f docker/docker-compose.yml --env-file .env --profile obs up -d prometheus grafana
```

| Service | Port | Config |
|---------|------|--------|
| `prometheus` | **9090** | `docker/observability/prometheus.yml` scrapes `api:8000/metrics` |
| `grafana` | **3000** | Default login `admin` / `admin` (override via env) |

Prometheus job:

```yaml
scrape_configs:
  - job_name: aibi-api
    static_configs:
      - targets: ["api:8000"]
    metrics_path: /metrics
```

## API readiness

```
GET /health/ready
```

Used by Compose healthchecks and release smokes.

## Logging

`LOG_FORMAT=json` emits structured logs suitable for Loki/ELK (T-08). Wave 2 does not
ship a log aggregator in Compose; wire your collector to container stdout.

See [OPS_CONFIG_MATRIX.md](./OPS_CONFIG_MATRIX.md) for env variables.
