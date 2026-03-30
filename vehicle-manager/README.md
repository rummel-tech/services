# Vehicle Manager API

Vehicle maintenance, fuel, and mileage tracking microservice for the Artemis platform.

## Overview

Manages vehicles (stored as typed assets), maintenance records, and fuel records. Calculates MPG automatically on fuel entry and provides per-vehicle cost/usage statistics.

**Port:** 8030

## Quick Start

```bash
cd vehicle-manager
pip install -r requirements.txt
DATABASE_URL=sqlite:///./dev.db uvicorn main:app --port 8030 --reload
```

Without `ARTEMIS_AUTH_URL` set the service runs in dev fallback mode (no real auth check).

## Authentication

All endpoints except `/health` and `/ready` require a Bearer JWT issued by the auth service.

```
Authorization: Bearer <access_token>
```

## Endpoints

### Vehicles

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/vehicles/{user_id}` | List all vehicles for user |
| POST | `/vehicles` | Create a vehicle |
| GET | `/vehicles/{user_id}/{vehicle_id}` | Get a specific vehicle |
| DELETE | `/vehicles/{user_id}/{vehicle_id}` | Delete a vehicle |

### Maintenance

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/maintenance/{vehicle_id}` | List maintenance records for vehicle |
| POST | `/maintenance` | Create a maintenance record |
| DELETE | `/maintenance/{vehicle_id}/{record_id}` | Delete a maintenance record |

### Fuel

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/fuel/{vehicle_id}` | List fuel records; optional `?limit=` |
| POST | `/fuel` | Create a fuel record (MPG calculated automatically) |
| DELETE | `/fuel/{vehicle_id}/{record_id}` | Delete a fuel record |

### Statistics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/stats/{vehicle_id}` | Fuel and maintenance cost/usage stats for a vehicle |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |

### Artemis Integration

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/artemis/manifest` | No | Module manifest for the platform shell |
| GET | `/artemis/summary/{user_id}` | Bearer | Vehicle fleet summary |
| GET | `/artemis/data/...` | Bearer | Data endpoints for platform widgets |

## Data Models

### Vehicle (Asset)

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | |
| `user_id` | string | |
| `name` | string | Display name (e.g. "2020 Camry") |
| `manufacturer` | string | Make |
| `model_number` | string | Model |
| `serial_number` | string | Optional |
| `vin` | string | Optional |
| `purchase_date` | date | Optional |
| `purchase_price` | float | Optional |
| `condition` | string | `new`, `good`, `fair`, `poor` |
| `location` | string | Optional |

### MaintenanceRecord

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | |
| `asset_id` | UUID | Vehicle ID |
| `user_id` | string | |
| `maintenance_type` | string | e.g. `oil_change`, `tire_rotation` |
| `date` | datetime | |
| `cost` | float | Optional |
| `description` | string | Optional |
| `performed_by` | string | Optional |
| `next_due_date` | date | Optional |
| `next_due_mileage` | int | Optional |

### FuelRecord

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | |
| `asset_id` | UUID | Vehicle ID |
| `user_id` | string | |
| `date` | datetime | |
| `mileage` | int | Odometer reading |
| `gallons` | float | |
| `cost` | float | Total fill-up cost |
| `price_per_gallon` | float | Calculated if not provided |
| `fuel_type` | string | `regular`, `premium`, `diesel`, etc. |
| `mpg` | float | Calculated from previous fill-up |
| `notes` | string | Optional |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./dev.db` | SQLite or PostgreSQL connection string |
| `ARTEMIS_AUTH_URL` | — | Auth service base URL (e.g. `http://localhost:8090`). Omit for dev fallback mode. |

## Docker

```bash
# From services/ root
docker build -f vehicle-manager/Dockerfile -t vehicle-manager .
docker run -p 8030:8030 -e DATABASE_URL=sqlite:///./dev.db vehicle-manager
```

## Docker Compose

```bash
# From services/ root
docker compose up vehicle-manager
```
