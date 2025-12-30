# Home Manager API

Weekly home task management and goal tracking microservice.

## Overview

The Home Manager API provides endpoints for managing household tasks, organizing chores by category, and tracking home-related goals. It integrates with the common services package for standardized middleware, error handling, and health checks.

## Tech Stack

- **Framework**: FastAPI
- **Server**: Uvicorn ASGI
- **Validation**: Pydantic
- **Port**: 8020

## Quick Start

```bash
# From services directory
cd home-manager

# Install dependencies
pip install -r requirements.txt

# Run the service
uvicorn main:app --port 8020 --reload
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tasks/weekly/{user_id}` | Get all weekly tasks |
| GET | `/tasks/today/{user_id}` | Get today's tasks |
| GET | `/tasks/category/{user_id}/{category}` | Get tasks by category |
| GET | `/goals/{user_id}` | Get user goals |
| GET | `/stats/{user_id}` | Get task/goal statistics |
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |
| GET | `/docs` | Swagger UI documentation |

## Data Models

### Task
```json
{
  "id": "string",
  "title": "Laundry",
  "description": "optional description",
  "day": "Monday",
  "category": "chores",
  "priority": "high|medium|low",
  "completed": false,
  "estimated_minutes": 60
}
```

### Goal
```json
{
  "id": "string",
  "title": "Organize Garage",
  "description": "Sort through items...",
  "category": "organizing",
  "target_date": "2025-12-31",
  "progress": 25,
  "is_active": true
}
```

## Task Categories

- `chores` - Regular household chores
- `cleaning` - Cleaning tasks
- `errands` - Outside errands
- `maintenance` - Home maintenance
- `cooking` - Meal prep and cooking
- `organizing` - Organization projects
- `outdoor` - Yard and outdoor work
- `planning` - Planning and scheduling

## Configuration

Uses the shared `common` package for:
- CORS middleware
- Security headers
- Request logging with correlation IDs
- Standardized error handling

## Docker

```bash
docker build -t home-manager .
docker run -p 8020:8020 home-manager
```

## Related Services

- **Workout Planner API** (port 8000) - Fitness planning
- **Meal Planner API** (port 8010) - Meal planning
- **Vehicle Manager API** (port 8030) - Vehicle tracking
