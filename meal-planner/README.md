# Meal Planner API

Nutrition and meal tracking microservice for the Artemis platform.

## Overview

Tracks individual meal entries with nutritional data. Provides daily summaries, date-range queries, and a 7-day meal plan view. Integrates with the Artemis platform manifest/summary system.

**Port:** 8010

## Quick Start

```bash
cd meal-planner
pip install -r requirements.txt
DATABASE_URL=sqlite:///./dev.db uvicorn main:app --port 8010 --reload
```

Without `ARTEMIS_AUTH_URL` set the service runs in dev fallback mode (no real auth check).

## Authentication

All endpoints except `/health`, `/ready`, and `/artemis/manifest` require a Bearer JWT issued by the auth service.

```
Authorization: Bearer <access_token>
```

## Endpoints

### Meals

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/meals/{user_id}` | List meals; optional `?start_date=` and `?end_date=` |
| POST | `/meals` | Create a meal entry |
| GET | `/meals/today/{user_id}` | Daily meals and nutrition totals; optional `?meal_date=` |
| GET | `/meals/weekly-plan/{user_id}` | 7-day meal plan; optional `?week_start=` |
| DELETE | `/meals/{user_id}/{meal_id}` | Delete a meal entry |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |

### Artemis Integration

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/artemis/manifest` | No | Module manifest for the platform shell |
| GET | `/artemis/summary/{user_id}` | Bearer | Daily nutrition summary |
| GET | `/artemis/data/daily_calories` | Bearer | Daily calorie data for charts |

## Data Models

### MealItem

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | |
| `user_id` | string | |
| `name` | string | Food name |
| `meal_type` | string | `breakfast`, `lunch`, `dinner`, `snack` |
| `date` | date | YYYY-MM-DD |
| `calories` | int | Optional |
| `protein_g` | int | Optional |
| `carbs_g` | int | Optional |
| `fat_g` | int | Optional |
| `notes` | string | Optional |

### DailyMeals (response from `/meals/today/{user_id}`)

```json
{
  "date": "2026-03-29",
  "meals": [...],
  "total_calories": 1800,
  "total_protein": 120,
  "total_carbs": 200,
  "total_fat": 60
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./dev.db` | SQLite or PostgreSQL connection string |
| `ARTEMIS_AUTH_URL` | — | Auth service base URL (e.g. `http://localhost:8090`). Omit for dev fallback mode. |
| `WORKOUT_PLANNER_URL` | — | Optional. Enables calories_burned cross-module lookup. |

## Docker

```bash
# From services/ root
docker build -f meal-planner/Dockerfile -t meal-planner .
docker run -p 8010:8010 -e DATABASE_URL=sqlite:///./dev.db meal-planner
```

## Docker Compose

```bash
# From services/ root
docker compose up meal-planner
```
