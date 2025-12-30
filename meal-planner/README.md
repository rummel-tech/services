# Meal Planner API

Weekly meal planning and nutrition tracking microservice.

## Overview

The Meal Planner API provides endpoints for managing weekly meal plans with nutritional information. It integrates with the common services package for standardized middleware, error handling, and health checks.

## Tech Stack

- **Framework**: FastAPI
- **Server**: Uvicorn ASGI
- **Validation**: Pydantic
- **Port**: 8010

## Quick Start

```bash
# From services directory
cd meal-planner

# Install dependencies
pip install -r requirements.txt

# Run the service
uvicorn main:app --port 8010 --reload
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/meals/weekly-plan/{user_id}` | Get weekly meal plan |
| GET | `/meals/today/{user_id}` | Get today's meals |
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |
| GET | `/docs` | Swagger UI documentation |

## Data Models

### MealItem
```json
{
  "name": "string",
  "calories": 350,
  "protein_g": 20,
  "carbs_g": 45,
  "fat_g": 12
}
```

### WeeklyMealPlan
```json
{
  "user_id": "string",
  "week_start": "2025-01-01",
  "focus": "balanced",
  "days": [
    {
      "day": "Monday",
      "meals": [MealItem]
    }
  ]
}
```

## Configuration

Uses the shared `common` package for:
- CORS middleware
- Security headers
- Request logging with correlation IDs
- Standardized error handling

## Docker

```bash
docker build -t meal-planner .
docker run -p 8010:8010 meal-planner
```

## Related Services

- **Workout Planner API** (port 8000) - Fitness planning
- **Home Manager API** (port 8020) - Home task management
- **Vehicle Manager API** (port 8030) - Vehicle tracking
