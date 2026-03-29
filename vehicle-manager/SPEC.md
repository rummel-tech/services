# Vehicle Manager — Module Specification

> **Scope:** This document covers the `services/vehicle-manager` FastAPI backend.
> For the Flutter frontend, see `modules/asset-managers/vehicle-manager/`.
> For the platform-wide integration contract, see `rummel-tech/resources/ARTEMIS_MODULE_CONTRACT.md`.

---

## 1. Purpose & Domain

Vehicle Manager tracks a fleet of user-owned vehicles, their maintenance history,
fuel consumption, and service schedules. It operates both as a fully independent
application and as a module within the Artemis Personal OS platform.

**Core responsibilities:**
- Store vehicle profiles (make, model, year, VIN, condition)
- Log fuel fill-ups with mileage, cost, and fuel-economy calculation
- Record maintenance services with cost and next-due scheduling
- Surface upcoming maintenance and fleet cost summaries

**Out of scope for this service:**
- Insurance and registration document storage (future feature)
- Roadside assistance or emergency contacts
- Navigation or trip logging
- Dealer/service-centre CRM

---

## 2. Technology Stack

| Layer | Technology |
|-------|-----------|
| Framework | Python 3.11+, FastAPI |
| Server | Uvicorn |
| Database (prod) | PostgreSQL 15 |
| Database (dev/test) | SQLite 3 |
| Auth (Artemis mode) | RS256 JWT, `iss == "artemis-auth"` |
| Auth (standalone) | **Not yet implemented** — see §6 |
| Shared packages | `services/common` (database, models, middleware) |
| Port | **8030** |

---

## 3. Database Schema

### `assets` (vehicles)

Vehicle profiles. The table name is `assets` — inherited from the common model —
with `asset_type = 'vehicle'` to distinguish from other asset types.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID / TEXT | Primary key |
| `user_id` | VARCHAR(255) | JWT `sub` claim |
| `name` | VARCHAR(255) | User-chosen name, e.g. "My F-150" |
| `description` | TEXT | Optional |
| `asset_type` | VARCHAR(100) | Always `vehicle` for this service |
| `category` | VARCHAR(100) | `car`, `truck`, `motorcycle`, `rv`, etc. |
| `manufacturer` | VARCHAR(100) | Make, e.g. "Ford" |
| `model_number` | VARCHAR(100) | Model, e.g. "F-150" |
| `serial_number` | VARCHAR(100) | Optional |
| `vin` | VARCHAR(17) | Vehicle Identification Number |
| `purchase_date` | DATE / TEXT | |
| `purchase_price` | REAL | |
| `current_value` | REAL | Estimated current market value |
| `condition` | VARCHAR(50) | `excellent`, `good`, `fair`, `poor`, `needs_repair` |
| `location` | VARCHAR(100) | e.g. "Home garage" |
| `notes` | TEXT | |
| `context` | JSONB / TEXT | Additional metadata |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Indexes:** `user_id`, `asset_type`, `vin`

### `maintenance_records`

One row per service event.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID / TEXT | Primary key |
| `user_id` | VARCHAR(255) | Denormalised for query efficiency |
| `asset_id` | UUID / TEXT | FK → `assets.id` (CASCADE DELETE) |
| `maintenance_type` | VARCHAR(100) | `oil_change`, `tire_rotation`, `brakes`, `inspection`, etc. |
| `date` | DATE / TEXT | Date service was performed |
| `cost` | REAL | Total service cost |
| `description` | TEXT | e.g. "5W-30 full synthetic, 5 quarts" |
| `performed_by` | VARCHAR(255) | Tech or shop name |
| `next_due_date` | DATE / TEXT | When next service is due (calendar) |
| `next_due_mileage` | INTEGER | When next service is due (odometer) |
| `notes` | TEXT | |
| `context` | JSONB / TEXT | |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Indexes:** `asset_id`, `user_id`, `date`

### `fuel_records`

One row per fill-up.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID / TEXT | Primary key |
| `user_id` | VARCHAR(255) | Denormalised |
| `asset_id` | UUID / TEXT | FK → `assets.id` (CASCADE DELETE) |
| `date` | TEXT | ISO timestamp of fill-up |
| `mileage` | INTEGER | **Odometer reading at fill-up** (not trip miles) |
| `gallons` | REAL | Volume of fuel added |
| `cost` | REAL | Total cost of fill-up |
| `price_per_gallon` | REAL | Computed on insert: `cost / gallons` |
| `fuel_type` | VARCHAR(50) | `regular`, `premium`, `diesel`; defaults to `regular` |
| `mpg` | REAL | Fuel economy for this tank (computed from odometer delta) |
| `notes` | TEXT | |
| `created_at` | TIMESTAMP | |

**Indexes:** `asset_id`, `user_id`, `date`

> **MPG calculation:** `mpg` is not currently auto-computed on insert. The
> `agent_get_vehicle_stats` endpoint reads `AVG(mpg)` from stored records, so if `mpg`
> is never written, stats will show 0. Implement MPG calculation on fuel insert:
> `mpg = (current_mileage - previous_mileage) / gallons`.

### Running Migrations

```bash
# Against local SQLite (dev)
DATABASE_URL=sqlite:///vehicle-manager.db python migrate_db.py

# Against PostgreSQL (prod)
DATABASE_URL=postgresql://user:pass@host/dbname python migrate_db.py
```

---

## 4. Standalone API

> **Auth gap:** Endpoints currently accept any `user_id` without verification.
> See §6 for the standalone auth implementation plan.

### Vehicle (Asset) Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/vehicles/{user_id}` | List all vehicles for user |
| `POST` | `/vehicles` | Create a vehicle profile |
| `GET` | `/vehicles/{user_id}/{vehicle_id}` | Get a specific vehicle |
| `PUT` | `/vehicles/{user_id}/{vehicle_id}` | Update a vehicle |
| `DELETE` | `/vehicles/{user_id}/{vehicle_id}` | Delete a vehicle |

#### Create Vehicle

```json
// POST /vehicles
// Body (AssetCreate model — asset_type forced to "vehicle")
{
  "user_id": "user_abc",
  "name": "Daily Driver",
  "asset_type": "vehicle",
  "category": "car",
  "manufacturer": "Toyota",
  "model_number": "Camry",
  "vin": "1HGCM82633A123456",
  "condition": "good",
  "purchase_date": "2022-06-15",
  "purchase_price": 28000
}
// Response 201 — full Asset object
```

> **Known issue:** The `POST /vehicles` response currently fails with a Pydantic
> `ValidationError` in SQLite mode because `context` is stored as the string `'{}'`
> but the `Asset` model expects a `dict`. This does not affect the Artemis endpoints.
> Fix: store context as JSON and parse it back on read, or use `context TEXT DEFAULT '{}'`
> with explicit JSON parsing in `dict_from_row`. See §12.

### Maintenance Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/maintenance/{vehicle_id}` | All maintenance records for a vehicle |
| `GET` | `/maintenance/{vehicle_id}/type/{service_type}` | Filter by type |
| `GET` | `/schedule/{vehicle_id}` | Upcoming scheduled maintenance |
| `POST` | `/maintenance` | Log a maintenance record |
| `PUT` | `/maintenance/{record_id}` | Update a record |

### Fuel Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/fuel/{vehicle_id}` | All fuel records for a vehicle |
| `POST` | `/fuel` | Log a fill-up |

### Statistics Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/stats/{vehicle_id}` | Fuel economy and maintenance cost summary |
| `GET` | `/summary/{user_id}` | Fleet-wide summary across all vehicles |

### Utility Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness probe |
| `GET /ready` | Readiness probe with db status |
| `GET /` | Service info |
| `GET /docs` | Swagger UI |

---

## 5. Artemis Integration (Contract v1.0)

All Artemis endpoints are implemented in `routers/artemis.py`. The contract is
**fully implemented** as of March 2026.

### Auth in Artemis Mode

Accepts `Authorization: Bearer <token>` where `iss == "artemis-auth"`. Validates
against the RS256 public key from the auth service at `ARTEMIS_AUTH_URL`.

```bash
ARTEMIS_AUTH_URL=http://localhost:8090   # default
```

Dev fallback: when the auth service is unreachable, token claims are accepted
without signature verification. Never expose this fallback in production.

### `GET /artemis/manifest`

No auth required. The manifest declares:
- **Widgets:** `fleet_overview` (small), `upcoming_maintenance` (medium)
- **Quick actions:** `log_fuel`
- **Data provided:** `fuel_costs` (permission: `vehicle.fuel.read`), `maintenance_costs` (permission: `vehicle.maintenance.read`)
- **Agent tools:** `list_vehicles`, `log_fuel`, `log_maintenance`, `get_vehicle_stats`

### `GET /artemis/widgets/{widget_id}`

| Widget ID | Data Returned |
|-----------|--------------|
| `fleet_overview` | `vehicle_count`, first 3 vehicles `{id, name, manufacturer, model_number, condition}`, condition breakdown dict |
| `upcoming_maintenance` | Up to 5 upcoming maintenance items, sorted by `next_due_date`, each with `vehicle_name`, `maintenance_type`, `next_due_date`, `cost` |

### `POST/GET /artemis/agent/{tool_id}`

| Tool ID | Method | Required params | What it does |
|---------|--------|-----------------|--------------|
| `list_vehicles` | GET or POST | — | Lists all vehicles in user's fleet |
| `log_fuel` | POST | `vehicle_id`, `mileage`, `gallons`, `cost` | Logs a fill-up; computes `price_per_gallon`; `fuel_type`, `notes` optional |
| `log_maintenance` | POST | `vehicle_id`, `maintenance_type` | Logs a service; `cost`, `description`, `next_due_date` optional |
| `get_vehicle_stats` | POST | `vehicle_id` | Returns fuel fill-up count, total cost, total gallons, avg MPG; maintenance count, total cost, last service date |

All tools return:
```json
{ "success": true, "result": { ... }, "message": "..." }
```

### `GET /artemis/data/{data_id}`

| Data ID | Permission Required | Schema |
|---------|--------------------|----|
| `fuel_costs` | `vehicle.fuel.read` | `total_cost`, `total_gallons`, `avg_mpg` (rolling, all-time) |
| `maintenance_costs` | `vehicle.maintenance.read` | `total_cost`, `service_count` (rolling, all-time) |

---

## 6. Standalone Auth — Implementation Plan

Currently unauthenticated. To operate as a standalone app:

1. Add a `users` table or use the future shared auth service
2. Expose `POST /auth/register` and `POST /auth/login`
3. Issue JWTs with `iss: "vehicle-manager"`
4. Protect all standalone endpoints with `require_standalone_token`
5. The Artemis `require_token` in `routers/artemis.py` already handles Artemis JWTs;
   extend it to also accept `iss: "vehicle-manager"` for standalone compatibility

**Priority:** High — do not expose publicly without auth.

---

## 7. Local Development

### Setup

```bash
cd services/vehicle-manager
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create the SQLite dev database
DATABASE_URL=sqlite:///vehicle-manager.db python migrate_db.py

# Run the server
DATABASE_URL=sqlite:///vehicle-manager.db uvicorn main:app --reload --port 8030
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///app.db` | Database connection string |
| `ARTEMIS_AUTH_URL` | `http://localhost:8090` | Artemis auth service URL |

### Seeding Test Data

The Artemis test suite inserts vehicles directly via SQLite for reliability. For
manual testing, use the Swagger UI at `http://localhost:8030/docs`.

---

## 8. Testing

```bash
source .venv/bin/activate
pytest tests/ -v
```

### Test Strategy

- **`tests/test_artemis.py`** — 15 integration tests for the Artemis contract.
  Seeds a vehicle directly via SQLite (bypassing the native API, which has the
  `context` JSON issue). Covers all widgets, all 4 agent tools, and both data
  endpoints.

- **`tests/test_vehicles.py`** — Tests for the standalone vehicle API.

The `vehicle_id` fixture inserts directly into the SQLite database:
```python
conn.execute(
    "INSERT INTO assets (id, user_id, name, asset_type, ...) VALUES (?,?,?,?,...)",
    (vid, TEST_USER, "Test Truck", "vehicle", ...),
)
```

This pattern should be used for any test that depends on a pre-existing vehicle.

### Adding New Tests

```python
def test_log_fuel_partial_data(client, vehicle_id):
    r = client.post("/artemis/agent/log_fuel", headers=AUTH, json={
        "vehicle_id": vehicle_id,
        "mileage": 50000,
        "gallons": 12.5,
        "cost": 45.00,
    })
    assert r.status_code == 200
    assert r.json()["result"]["price_per_gallon"] == round(45.00 / 12.5, 3)
```

---

## 9. Deployment

```dockerfile
# Dockerfile — already present
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8030"]
```

**Production:**
- AWS ECS Fargate via `rummel-tech/infrastructure`
- Production URL: `https://api.rummeltech.com/vehicle-manager`
- Database: Amazon RDS PostgreSQL
- Env vars via AWS Secrets Manager

---

## 10. Feature Roadmap

### Standalone Enhancements

| Priority | Feature | Notes |
|----------|---------|-------|
| ~~High~~ | ~~Standalone JWT auth (§6)~~ | ✅ Done |
| ~~High~~ | ~~Auto-compute MPG on fuel insert~~ | ✅ Done |
| ~~High~~ | ~~Fix `context` JSON bug on vehicle create~~ | ✅ Done |
| Medium | Mileage-based maintenance reminders | Alert when `next_due_mileage` < current_mileage + 500 |
| Medium | Date-based maintenance reminders | Alert when `next_due_date` is within 14 days |
| Medium | Lifetime cost summary | Total fuel + maintenance cost per vehicle |
| Medium | Vehicle condition history | Track condition changes over time |
| Low | Odometer tracking | Dedicated mileage log separate from fuel records |
| Low | Insurance & registration tracking | Expiry dates and document storage |
| Low | Recall lookups | Query NHTSA API by VIN |

### Artemis Enhancements

| Priority | Feature | Notes |
|----------|---------|-------|
| ✅ Done | `GET /artemis/summary` | Natural language fleet briefing |
| ✅ Done | `GET /artemis/calendar` | Upcoming maintenance as calendar events |
| Medium | `provides_data: maintenance_schedule` | Structured upcoming services for Artemis calendar |
| Medium | `update_mileage` agent tool | Let AI agent update current odometer reading |
| Low | `GET /artemis/notifications` | Alert when a maintenance item is overdue |
| Low | Date-range fuel cost queries | `/artemis/data/fuel_costs?start=&end=` |

### Schema Evolution (Future)

A `maintenance_schedules` table for interval-based reminders (e.g. "every 5000 miles") would complement the current `maintenance_records` log. Columns: `asset_id`, `service_type`, `interval_miles`, `interval_months`, `next_due_mileage`, `next_due_date`.

---

## 11. Cross-Module Data

### Provides

| Data ID | Permission | Description | Used By |
|---------|-----------|-------------|---------|
| `fuel_costs` | `vehicle.fuel.read` | Rolling fuel spend (all-time) | artemis-agent |
| `maintenance_costs` | `vehicle.maintenance.read` | Rolling maintenance spend (all-time) | artemis-agent |
| `maintenance_schedule` *(planned)* | `vehicle.schedule.read` | Upcoming services with dates | artemis-calendar |
| `vehicle_summary` *(planned)* | `vehicle.fleet.read` | Fleet count and overall condition | artemis-agent |

### Consumes

Vehicle Manager has no mandatory cross-module data dependencies. Future option:
- Consume location/trip data from a hypothetical trip-logger module for odometer updates

---

## 12. Known Issues & Tech Debt

| Issue | Severity | Notes |
|-------|----------|-------|
| ~~No standalone auth~~ | ~~High~~ | ✅ Fixed — `require_token` added to all endpoints |
| ~~`context` stored as string, not JSON, in SQLite~~ | ~~High~~ | ✅ Fixed — `json.dumps` on insert, `json.loads` on read |
| ~~`mpg` field never written on fuel insert~~ | ~~Medium~~ | ✅ Fixed — MPG computed from previous mileage record on insert |
| Artemis data endpoints return all-time totals only | Medium | No date-range filtering; callers can't get monthly breakdowns |
| `migrate_db.py` uses PostgreSQL syntax | Medium | Can't run against SQLite — tests create schema inline as a workaround |
| `fuel_records.date` stores ISO timestamp, not just date | Low | Queries that group by day need `DATE(date)` in PostgreSQL |
| `list_vehicles` exposes `GET /artemis/agent/list_vehicles` | Info | Read-only tools should prefer GET for cache-friendliness — already correct |

### `context` Fix — Recommended Implementation

In `main.py` `create_vehicle`, change the INSERT to store JSON and parse on fetch:

```python
import json

# On insert
str(json.dumps(vehicle.context))  # instead of str(vehicle.context)

# In dict_from_row for SQLite rows
if 'context' in row_dict and isinstance(row_dict['context'], str):
    try:
        row_dict['context'] = json.loads(row_dict['context'])
    except (json.JSONDecodeError, TypeError):
        row_dict['context'] = {}
```

---

*Specification last updated: March 2026*
*Artemis contract version implemented: 1.0*
