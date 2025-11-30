# Fitness AI FastAPI Backend

## Overview
This FastAPI service provides AI-driven fitness planning (daily & weekly plans), readiness scoring, strength/swim/murph metric processing, goal management, and simple auth + chat endpoints. It supports both local SQLite development and production PostgreSQL (e.g. AWS RDS) with automatic schema bootstrap.

## Quick Start (Local Dev)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///fitness_dev.db
uvicorn main:app --reload --port 8000
```
Visit: http://localhost:8000/docs

## Environment Variables
| Variable | Purpose | Example |
|----------|---------|---------|
| `DATABASE_URL` | DB connection (Postgres or SQLite) | `postgresql://user:pass@host:5432/postgres` |
| `JWT_SECRET` | JWT signing secret | `super_long_random_value` |
| `ENVIRONMENT` | App environment (`development`/`staging`/`production`) | `production` |
| `LOG_LEVEL` | Logging level | `info` |

All values can be injected via a `.env` file or container secrets. In production, secrets should come from AWS Secrets Manager.

## Database
- SQLite: Auto-created file + schema migrations handled in `database.py`.
- Postgres: `database.py` initializes tables idempotently on first import using `IF NOT EXISTS`.
- To disable auto-init (managed migrations), set `DISABLE_DB_AUTO_INIT=1` (future toggle, not yet implemented).

## Health & Readiness
- `GET /health` basic liveness.
- `GET /ready` performs a DB connectivity check and returns `db: ok|error`.

## Persistence Endpoints
- `GET/PUT/DELETE /daily-plans/...` per-day workout plans.
- `GET/PUT/DELETE /weekly-plans/...` per-week schedule.

## Production Container
Build & run locally to test Docker image:
```bash
docker build -t fitness-ai-backend .
docker run -p 8000:8000 -e DATABASE_URL=sqlite:///fitness_dev.db fitness-ai-backend
```

## Metrics
- `GET /metrics` exposes Prometheus metrics (request latencies, domain events).

### Gunicorn/Uvicorn Metrics
When running in production, the application server itself can expose valuable metrics. To enable this, you can use the `prometheus_client` library to run an independent metrics server.

**Example with Gunicorn:**
```bash
# In your wsgi.py or equivalent entrypoint
from prometheus_client import start_http_server
from main import app

# Start a Prometheus metrics server on a separate port
start_http_server(8001)

# To run with Gunicorn:
# gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
```

Your Prometheus configuration would then need to scrape both the application's `/metrics` endpoint and the separate metrics server on port 8001.

## Logging
Structured logs include correlation IDs (`X-Request-ID` header) for traceability.

## Future Hardening
- JWT auth enforcement across protected endpoints.
- Rate limiting & API keys.
- Managed migrations instead of auto-init.
- Background tasks queue (Celery / RQ) for heavy AI ops.

## Troubleshooting
| Symptom | Cause | Fix |
|---------|-------|-----|
| `readiness: degraded` | DB unreachable | Verify `DATABASE_URL`, security group, RDS status |
| SQLite file missing | Wrong working directory | Check path & ensure `sqlite:///` URL correct |
| ImportError psycopg2 | Missing system libs | Install `libpq-dev` (Dockerfile already handles) |

## License
Internal / Proprietary (do not distribute).
