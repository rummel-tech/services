# Vehicle Manager API

Vehicle maintenance, fuel, and mileage tracking microservice.

## Overview

The Vehicle Manager API provides comprehensive endpoints for managing vehicles, tracking maintenance schedules, logging fuel consumption, and analyzing vehicle statistics. It integrates with the common services package for standardized middleware, error handling, and health checks.

## Tech Stack

- **Framework**: FastAPI
- **Server**: Uvicorn ASGI
- **Validation**: Pydantic
- **Port**: 8030

## Quick Start

```bash
# From services directory
cd vehicle-manager

# Install dependencies
pip install -r requirements.txt

# Run the service
uvicorn main:app --port 8030 --reload
```

## API Endpoints

### Vehicles
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/vehicles/{user_id}` | Get all user vehicles |
| GET | `/vehicles/{user_id}/{vehicle_id}` | Get specific vehicle |

### Maintenance
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/maintenance/{vehicle_id}` | Get maintenance records |
| GET | `/maintenance/{vehicle_id}/type/{service_type}` | Get records by type |
| GET | `/schedule/{vehicle_id}` | Get maintenance schedule |

### Fuel
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/fuel/{vehicle_id}` | Get fuel records |

### Statistics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/stats/{vehicle_id}` | Get vehicle statistics |
| GET | `/summary/{user_id}` | Get summary for all vehicles |

### Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |
| GET | `/docs` | Swagger UI documentation |

## Data Models

### Vehicle
```json
{
  "id": "v1",
  "make": "Toyota",
  "model": "Camry",
  "year": 2020,
  "vin": "1HGBH41JXMN109186",
  "license_plate": "ABC-1234",
  "current_mileage": 45000,
  "color": "Silver"
}
```

### MaintenanceRecord
```json
{
  "id": "m1",
  "vehicle_id": "v1",
  "date": "2025-10-15",
  "type": "oil_change",
  "mileage": 42000,
  "cost": 45.99,
  "description": "Synthetic oil change",
  "next_due_mileage": 47000,
  "next_due_date": "2026-04-15"
}
```

### FuelRecord
```json
{
  "id": "f1",
  "vehicle_id": "v1",
  "date": "2025-11-18",
  "mileage": 45000,
  "gallons": 12.5,
  "cost": 43.75,
  "price_per_gallon": 3.50,
  "fuel_type": "regular",
  "mpg": 28.4
}
```

### MaintenanceSchedule
```json
{
  "id": "s1",
  "vehicle_id": "v1",
  "service_type": "Oil Change",
  "interval_miles": 5000,
  "last_service_mileage": 42000,
  "next_due_mileage": 47000,
  "status": "upcoming|due|overdue"
}
```

## Maintenance Types

- `oil_change` - Oil and filter changes
- `tire_rotation` - Tire rotation and balancing
- `brake_service` - Brake pad/rotor service
- `inspection` - State/safety inspections
- `air_filter` - Air filter replacement

## Configuration

Uses the shared `common` package for:
- CORS middleware
- Security headers
- Request logging with correlation IDs
- Standardized error handling

## Docker

```bash
docker build -t vehicle-manager .
docker run -p 8030:8030 vehicle-manager
```

## Related Services

- **Workout Planner API** (port 8000) - Fitness planning
- **Meal Planner API** (port 8010) - Meal planning
- **Home Manager API** (port 8020) - Home task management
