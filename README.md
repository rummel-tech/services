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
pip install -e ../common  # Install shared package
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
├── common/                           # Shared utilities package
│   ├── __init__.py
│   ├── app_factory.py                # FastAPI app factory
│   ├── middleware.py                 # Standard middleware (CORS, security, logging)
│   ├── utils.py                      # Shared utilities (date parsing, etc.)
│   └── pyproject.toml                # Package configuration
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

## Common Package

The `common/` package provides shared functionality for all services:

### App Factory

```python
from common import create_app, ServiceConfig

config = ServiceConfig(
    name="my-service",
    title="My Service API",
    version="0.1.0",
    port=8000,
)

app = create_app(config)
```

This automatically adds:
- Standard health endpoints (`/health`, `/ready`, `/`)
- CORS middleware
- Security headers
- Request logging with correlation IDs
- Response time headers

### Utilities

```python
from common import day_name_from_date, parse_date

# Get day name from date string
day = day_name_from_date("2025-11-30")  # "Sunday"

# Parse date string to date object
d = parse_date("2025-11-30")  # date(2025, 11, 30)
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | deployment environment | `development` |
| `ROOT_PATH` | API root path prefix | (empty) |

## Development

All services now follow a standardized pattern:

- **FastAPI framework** with shared app factory
- **Uvicorn ASGI server**
- **Standard endpoints**: `/health`, `/ready`, `/`, `/docs`
- **Security headers**: X-Content-Type-Options, X-Frame-Options, etc.
- **Request tracking**: X-Request-ID correlation header
- **Response timing**: X-Response-Time-Ms header
- **CORS**: enabled for development

## API Documentation

When running, each service exposes:
- Swagger UI: `http://localhost:<PORT>/docs`
- ReDoc: `http://localhost:<PORT>/redoc`
- OpenAPI spec: `http://localhost:<PORT>/openapi.json`

## Testing

```bash
# Run tests for a specific service
cd workout-planner
pytest

# Run with coverage
pytest --cov=. --cov-report=term
```
