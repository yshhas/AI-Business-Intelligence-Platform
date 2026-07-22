# T-12 — API + Worker image (same artifact; role via APP_ROLE)
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    APP_ROLE=api \
    API_PORT=8000

WORKDIR /app

# System deps: curl for healthcheck; ca-certificates for HTTPS LLM calls
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/backend/requirements.txt

COPY agent /app/agent
COPY backend /app/backend
COPY docker/entrypoint.py /app/docker/entrypoint.py

# Persist uploads / DuckDB via compose volume at /app/data
RUN mkdir -p /app/data/uploads /app/data/duckdb

WORKDIR /app/backend
EXPOSE 8000 8001

ENTRYPOINT ["python", "/app/docker/entrypoint.py"]
