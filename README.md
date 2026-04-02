# Services

Backend microservices for the Rummel/Artemis platform. Each service is an
independently deployable FastAPI application that also implements the
**Artemis Module Contract** — exposing `/artemis/manifest`, widget, agent
tool, and cross-module data endpoints so the Artemis platform can discover
and orchestrate them.

## Architecture

```
                      ┌──────────────┐
                      │  Artemis     │ ← platform (discovery, agent, dashboard)
                      │  :8080       │
                      └─────┬────────┘
                            │ polls /artemis/manifest
        ┌───────────────────┼───────────────────────────┐
        ▼                   ▼                           ▼
  ┌────────────┐   ┌──────────────┐            ┌───────────────┐
  │ workout-   │   │ meal-planner │  ...       │ content-      │
  │ planner    │   │ :8010        │            │ planner :8060 │
  │ :8000      │   └──────────────┘            └───────────────┘
  └────────────┘
```

Every module is a **standalone application** — it can run, develop, and test
independently. Artemis integration is additive via `routers/artemis.py`.

## Services

| Service            | Port | Standalone Auth | Description |
|--------------------|------|-----------------|-------------|
| artemis            | 8080 | —               | Platform hub: module registry, dashboard, AI agent |
| auth               | 8090 | —               | Central RS256 JWT auth with Google OAuth |
| workout-planner    | 8000 | HS256           | AI-powered fitness coaching |
| meal-planner       | 8010 | —               | Nutrition tracking and meal planning |
| home-manager       | 8020 | —               | Property and household task management |
| vehicle-manager    | 8030 | —               | Vehicle fleet, maintenance, and fuel tracking |
| work-planner       | 8040 | HS256           | Task management, project tracking, work sessions |
| education-planner  | 8050 | HS256           | Goal-oriented learning management |
| content-planner    | 8060 | HS256           | Audio-first content consumption and queue management |

## Shared Infrastructure

### `common/` — Shared Python Library

All services share a common library providing production-ready features:

| Module            | What it provides |
|-------------------|-----------------|
| `app_factory.py`  | FastAPI app factory with health endpoints, metrics, CORS, security headers |
| `artemis_auth.py` | Dual-token auth (standalone HS256 + Artemis RS256) for module endpoints |
| `database.py`     | SQLite/PostgreSQL connection pooling with dialect abstraction |
| `middleware.py`    | Correlation IDs, request logging, response timing |
| `settings.py`     | Pydantic-based settings with env/secrets integration |
| `cache.py`        | Redis caching with graceful fallback |
| `aws_secrets.py`  | AWS Secrets Manager integration |
| `metrics.py`      | Prometheus metrics collection |

### Artemis Module Contract

Every service implements the contract via `routers/artemis.py`:

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /artemis/manifest` | None | Capability declaration (polled by platform) |
| `GET /artemis/widgets/{id}` | Required | Live widget data for Artemis dashboard |
| `POST /artemis/agent/{tool_id}` | Required | AI agent tool execution |
| `GET /artemis/data/{data_id}` | Required | Cross-module data sharing |
| `GET /artemis/summary` | Required | Natural language summary for AI briefings |
| `GET /artemis/calendar` | Required | Calendar events (next 14 days) |

Auth on protected endpoints accepts both the service's standalone JWT **and**
Artemis platform tokens (`iss: artemis-auth`, RS256). This is handled by
`common.artemis_auth.create_artemis_token_dependency()`.

## Quick Start

```bash
cd <service-name>
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ../common
uvicorn main:app --reload --port <PORT>
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | `development` / `staging` / `production` | `development` |
| `API_PREFIX` | ALB path-routing prefix (e.g. `/workout-planner`) | (empty) |
| `ARTEMIS_AUTH_URL` | Auth service URL for public key fetch | `http://localhost:8090` |
| `DATABASE_URL` | PostgreSQL connection string | service-specific SQLite |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |

## Directory Structure

```
services/
├── common/                     # Shared Python library
│   ├── app_factory.py          # FastAPI app factory
│   ├── artemis_auth.py         # Dual-token auth for module endpoints
│   ├── database.py             # DB abstraction
│   ├── middleware.py            # Correlation IDs, logging
│   └── ...
├── artemis/                    # Platform hub
├── auth/                       # Central auth service
├── workout-planner/            # Fitness coaching
├── meal-planner/               # Nutrition tracking
├── home-manager/               # Household management
├── vehicle-manager/            # Vehicle tracking
├── work-planner/               # Task & project management
├── education-planner/          # Learning management
└── content-planner/            # Content consumption tracking
```

## Testing

```bash
cd workout-planner
pytest
pytest --cov=. --cov-report=term
```

## API Documentation

Each running service exposes Swagger UI at `/docs` and ReDoc at `/redoc`.
