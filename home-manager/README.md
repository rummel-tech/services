# Home Manager API

Household task, goal, and asset management microservice for the Artemis platform.

## Overview

Manages tasks (to-dos with status/priority), goals (targets with optional progress tracking), and assets (physical items with condition/location). Integrates with the Artemis platform manifest/summary system.

**Port:** 8020

## Quick Start

```bash
cd home-manager
pip install -r requirements.txt
DATABASE_URL=sqlite:///./dev.db uvicorn main:app --port 8020 --reload
```

Without `ARTEMIS_AUTH_URL` set the service runs in dev fallback mode (no real auth check).

## Authentication

All endpoints except `/health` and `/ready` require a Bearer JWT issued by the auth service.

```
Authorization: Bearer <access_token>
```

## Endpoints

### Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tasks/{user_id}` | List all tasks for user |
| POST | `/tasks` | Create a task |
| GET | `/tasks/{user_id}/{task_id}` | Get a specific task |
| PUT | `/tasks/{user_id}/{task_id}` | Update a task |
| DELETE | `/tasks/{user_id}/{task_id}` | Delete a task |

### Goals

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/goals/{user_id}` | List all goals for user |
| POST | `/goals` | Create a goal |
| GET | `/goals/{user_id}/{goal_id}` | Get a specific goal |

### Assets

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/assets/{user_id}` | List assets; optional `?asset_type=` filter |
| POST | `/assets` | Create an asset |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |

### Artemis Integration

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/artemis/manifest` | No | Module manifest for the platform shell |
| GET | `/artemis/summary/{user_id}` | Bearer | Task/goal summary |
| GET | `/artemis/data/...` | Bearer | Data endpoints for platform widgets |

## Data Models

### Task

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | |
| `user_id` | string | |
| `title` | string | |
| `description` | string | Optional |
| `status` | string | `open`, `in_progress`, `done` |
| `priority` | string | `low`, `medium`, `high` |
| `category` | string | Optional |
| `due_date` | date | Optional |
| `estimated_minutes` | int | Optional |
| `tags` | list | Optional |

### Goal

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | |
| `user_id` | string | |
| `title` | string | |
| `description` | string | Optional |
| `category` | string | Optional |
| `target_value` | float | Optional |
| `target_unit` | string | Optional |
| `target_date` | date | Optional |
| `notes` | string | Optional |

### Asset

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | |
| `user_id` | string | |
| `name` | string | |
| `asset_type` | string | Freeform type label |
| `category` | string | Optional |
| `manufacturer` | string | Optional |
| `model_number` | string | Optional |
| `purchase_date` | date | Optional |
| `purchase_price` | float | Optional |
| `condition` | string | `new`, `good`, `fair`, `poor` |
| `location` | string | Optional |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./dev.db` | SQLite or PostgreSQL connection string |
| `ARTEMIS_AUTH_URL` | — | Auth service base URL (e.g. `http://localhost:8090`). Omit for dev fallback mode. |

## Docker

```bash
# From services/ root
docker build -f home-manager/Dockerfile -t home-manager .
docker run -p 8020:8020 -e DATABASE_URL=sqlite:///./dev.db home-manager
```

## Docker Compose

```bash
# From services/ root
docker compose up home-manager
```
