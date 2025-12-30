# Common Services Package

Shared utilities and base components for all FastAPI microservices.

## Overview

The `common` package provides standardized functionality across all services in the ecosystem, ensuring consistent behavior for application factory, middleware, error handling, and utilities.

## Installation

This package is used by adding the parent `services` directory to the Python path:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import create_app, ServiceConfig
```

## Components

### App Factory (`app_factory.py`)

Creates standardized FastAPI applications with consistent configuration.

```python
from common import create_app, ServiceConfig

config = ServiceConfig(
    name="my-service",
    title="My Service API",
    version="0.1.0",
    description="Service description",
    port=8000,
)

app = create_app(config)
```

#### ServiceConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | required | Service identifier |
| `title` | str | required | API title for docs |
| `version` | str | "0.1.0" | API version |
| `description` | str | "" | API description |
| `port` | int | 8000 | Default port |
| `root_path` | str | None | API root path (overridable via `ROOT_PATH` env) |
| `cors_origins` | list | ["*"] | Allowed CORS origins |
| `environment` | str | "development" | Current environment |
| `enable_security_headers` | bool | True | Add security headers |
| `enable_request_logging` | bool | True | Enable request logging |
| `enable_error_handlers` | bool | True | Install error handlers |

#### Auto-Generated Endpoints

Every app created with `create_app` includes:

| Endpoint | Description |
|----------|-------------|
| `GET /` | Service info (name, version, status) |
| `GET /health` | Basic health check |
| `GET /ready` | Readiness check |
| `GET /docs` | Swagger UI |
| `GET /redoc` | ReDoc documentation |

### Middleware (`middleware.py`)

Provides standard middleware for all services.

#### Security Headers

Automatically added to all responses:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Strict-Transport-Security` (production only)

#### Request Logging

Adds correlation IDs for request tracing:
- Generates unique `X-Request-ID` for each request
- Includes `X-Response-Time-Ms` in response headers
- Access current correlation ID: `get_correlation_id()`

```python
from common import get_correlation_id

@app.get("/example")
async def example():
    cid = get_correlation_id()
    # Use for logging, tracing, etc.
```

#### CORS

Configurable CORS middleware with sensible defaults.

### Error Handlers (`error_handlers.py`)

Standardized JSON error responses with:
- Timestamp
- Request path and method
- Status code
- Correlation ID
- Structured error information

#### Error Response Format

```json
{
  "timestamp": "2025-01-15T10:30:00Z",
  "path": "/api/resource",
  "method": "POST",
  "status_code": 422,
  "correlation_id": "abc-123-def",
  "error": {
    "type": "validation_error",
    "message": "Request validation failed",
    "details": [...]
  }
}
```

#### Handled Exception Types

- **HTTP Exceptions** (4xx, 5xx) - Standard HTTP errors
- **Validation Errors** (422) - Pydantic validation failures
- **Unhandled Exceptions** (500) - Generic server errors

### Utilities (`utils.py`)

Common helper functions.

```python
from common import day_name_from_date, parse_date

# Parse date string to date object
date_obj = parse_date("2025-01-15")  # Returns date object
date_obj = parse_date(None)          # Returns today

# Get day name from date
day = day_name_from_date("2025-01-15")  # "Wednesday"
day = day_name_from_date()              # Today's day name
```

## Exports

```python
from common import (
    create_app,           # App factory function
    ServiceConfig,        # Configuration dataclass
    day_name_from_date,   # Get day name from date string
    parse_date,           # Parse date string
    add_standard_middleware,  # Add middleware to existing app
    get_correlation_id,   # Get current request correlation ID
    install_error_handlers,   # Install error handlers on app
)
```

## Usage in Services

All microservices follow this pattern:

```python
"""
Example Service API
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from common import create_app, ServiceConfig

config = ServiceConfig(
    name="example-service",
    title="Example Service API",
    version="0.1.0",
    description="Example microservice",
    port=8000,
)

app = create_app(config)

@app.get("/example", tags=["Example"])
async def get_example():
    return {"message": "Hello"}
```

## Services Using This Package

- **Meal Planner** (port 8010)
- **Home Manager** (port 8020)
- **Vehicle Manager** (port 8030)
- **Workout Planner** (port 8000)
