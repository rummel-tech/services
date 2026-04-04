# Artemis Platform Service

Central platform hub that discovers, orchestrates, and aggregates data from all Artemis-compatible microservices. It exposes a unified dashboard API and a Claude-powered AI agent.

**Port:** 8080

## Overview

Artemis is stateless — it owns no user data. It fans out requests to registered module services and merges their responses. Modules register themselves via a YAML config file; Artemis polls each module's `/artemis/manifest` endpoint to discover capabilities.

**Core responsibilities:**
- Module registry: discover and health-check all registered modules on startup
- Dashboard aggregation: fan out to all module widget and summary endpoints
- AI agent: Claude-powered assistant with tools auto-generated from module manifests
- Token relay: forward the user's RS256 JWT to every module call

## Quick Start

```bash
cd services/artemis
pip install -r requirements.txt
ARTEMIS_AUTH_URL=http://localhost:8090 \
ANTHROPIC_API_KEY=<your-key> \
uvicorn main:app --port 8080 --reload
```

Without `ARTEMIS_AUTH_URL` set the service runs in dev fallback mode (no real auth check).

## Project Structure

```
artemis/
├── main.py                  # Application entry point
├── artemis/                 # Core platform logic
│   ├── agent.py             # Claude AI agent
│   ├── dashboard.py         # Dashboard aggregation
│   ├── registry.py          # Module registry
│   └── routers/             # API routers
├── config/
│   └── modules.yaml         # Registered module configuration
├── tests/                   # Test suite
├── requirements.txt
└── pyproject.toml
```

## Module Configuration

Edit `config/modules.yaml` to add, remove, or disable modules:

```yaml
modules:
  - id: workout-planner
    manifest_url: http://localhost:8000/artemis/manifest
    prod_manifest_url: https://api.rummeltech.com/workout-planner/artemis/manifest
    enabled: true

  - id: meal-planner
    manifest_url: http://localhost:8010/artemis/manifest
    prod_manifest_url: https://api.rummeltech.com/meal-planner/artemis/manifest
    enabled: true
```

## Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/artemis/modules` | Bearer | List all registered modules and their status |
| GET | `/artemis/dashboard/{user_id}` | Bearer | Aggregated dashboard from all modules |
| POST | `/artemis/agent` | Bearer | Chat with the AI agent |
| GET | `/health` | No | Health check |
| GET | `/ready` | No | Readiness check |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ARTEMIS_AUTH_URL` | `http://localhost:8090` | Auth service URL for public key fetch |
| `MODULES_CONFIG` | `config/modules.yaml` | Path to module registry config |
| `REGISTRY_REFRESH_SECONDS` | `300` | Background manifest re-poll interval (0 = disabled) |
| `ANTHROPIC_API_KEY` | — | Required for the AI agent |
| `AGENT_MODEL` | `claude-sonnet-4-6` | Claude model for the AI agent |
| `ENVIRONMENT` | `development` | Set to `production` for strict auth enforcement |

## Authentication

All data endpoints require a Bearer JWT issued by the auth service (`iss: artemis-auth`, RS256). In development, auth is bypassed when `ARTEMIS_AUTH_URL` is not set.

## Docker

```bash
# From services/ root
docker build -f artemis/Dockerfile -t artemis .
docker run -p 8080:8080 \
  -e ARTEMIS_AUTH_URL=http://host.docker.internal:8090 \
  -e ANTHROPIC_API_KEY=<your-key> \
  artemis
```

## Docker Compose

```bash
# From services/ root
docker compose up artemis
```

## Running Tests

```bash
cd artemis
pip install -r requirements.txt
pytest
```
