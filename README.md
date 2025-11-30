# Services

Centralized backend services for the Rummel app ecosystem.

## Services

| Service | Port | Description |
|---------|------|-------------|
| workout-planner | 8000 | AI-powered fitness coaching API |
| meal-planner | 8010 | Weekly meal planning API |
| home-manager | 8020 | Home task management API |
| vehicle-manager | 8030 | Vehicle maintenance tracking API |

## Quick Start

### Running a Single Service

```bash
cd <service-name>
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port <PORT>
```

### Running All Services

```bash
# From APP_DEV root
./start-all-apps.sh
```

## Structure

```
services/
├── workout-planner/                  # FastAPI - Main fitness coaching API
│   ├── main.py
│   ├── routers/                      # Modular API endpoints
│   ├── database.py                   # SQLite/PostgreSQL abstraction
│   └── tests/                        # Pytest suite
├── workout-planner-ai-engine/        # AI workout planning logic
├── workout-planner-fastapi-server/   # Alternative FastAPI server
├── workout-planner-integration-layer/ # Backend integration utilities
├── meal-planner/                     # FastAPI - Meal planning
│   └── main.py
├── home-manager/                     # FastAPI - Task management
│   └── main.py
└── vehicle-manager/                  # FastAPI - Vehicle tracking
    └── main.py
```

## Development

Each service follows the same pattern:
- FastAPI framework
- Uvicorn ASGI server
- Health endpoints at `/health` and `/ready`
- CORS enabled for development

## API Documentation

When running, each service exposes:
- Swagger UI: `http://localhost:<PORT>/docs`
- ReDoc: `http://localhost:<PORT>/redoc`
