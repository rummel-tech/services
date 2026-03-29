# Meal Planner — Module Specification

> **Scope:** This document covers the `services/meal-planner` FastAPI backend.
> For the Flutter frontend, see `modules/planners/meal-planner/`.
> For the platform-wide integration contract, see `rummel-tech/resources/ARTEMIS_MODULE_CONTRACT.md`.

---

## 1. Purpose & Domain

Meal Planner tracks daily nutrition intake and supports weekly meal planning. It is
designed to function both as a fully independent application and as a module within
the Artemis Personal OS platform.

**Core responsibilities:**
- Log meals with macro/calorie detail (breakfast, lunch, dinner, snacks)
- Aggregate daily and weekly nutrition summaries
- Store recurring weekly meal plans with a nutritional focus

**Out of scope for this service:**
- Recipe storage or ingredient management (future feature)
- Shopping list generation (future feature)
- Calorie *goals* or *targets* — those live in user preferences, not here
- Workout calorie burn — that comes from workout-planner via cross-module data

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
| Port | **8010** |

---

## 3. Database Schema

### `meals`

Primary table. One row per logged meal.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID / TEXT | Primary key |
| `user_id` | VARCHAR(255) | Opaque user identifier from JWT `sub` claim |
| `name` | VARCHAR(255) | Meal name, e.g. "Oatmeal with berries" |
| `meal_type` | VARCHAR(50) | `breakfast`, `lunch`, `dinner`, `snack` |
| `date` | DATE / TEXT | Local calendar date, ISO format `YYYY-MM-DD` |
| `calories` | INTEGER | Total calories for this meal |
| `protein_g` | INTEGER | Protein in grams |
| `carbs_g` | INTEGER | Carbohydrates in grams |
| `fat_g` | INTEGER | Fat in grams |
| `notes` | TEXT | Free-text notes |
| `created_at` | TIMESTAMP | Auto-set on insert |
| `updated_at` | TIMESTAMP | Auto-set on insert/update |

**Indexes:** `user_id`, `date`, `meal_type`

> **Important:** Always use local calendar date (`date.today()`) for the `date`
> column, not UTC date (`datetime.now(timezone.utc).date()`). Queries always filter
> on this same local date. Mixing the two causes meals to appear on the wrong day.

### `weekly_meal_plans`

Optional weekly plan records. Currently stores high-level intent (focus, notes)
rather than a full day-by-day meal schedule.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID / TEXT | Primary key |
| `user_id` | VARCHAR(255) | |
| `week_start` | DATE / TEXT | Monday of the planned week |
| `focus` | VARCHAR(100) | e.g. `balanced`, `high_protein`, `low_carb` |
| `notes` | TEXT | |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Indexes:** `user_id`, `week_start`

### Running Migrations

```bash
# Against local SQLite (dev)
DATABASE_URL=sqlite:///meal-planner.db python migrate_db.py

# Against PostgreSQL (prod)
DATABASE_URL=postgresql://user:pass@host/dbname python migrate_db.py
```

---

## 4. Standalone API

The standalone API is the service's native HTTP interface. All endpoints return JSON.

> **Auth gap:** These endpoints currently accept any user_id without verification.
> Standalone auth (standalone JWT issuance + validation) is not yet implemented.
> See §6 for the implementation plan.

### Meal Endpoints

#### `GET /meals/today/{user_id}`
Returns all meals logged for today for a user.

```json
// Response 200
{
  "user_id": "user_abc",
  "date": "2026-03-28",
  "meals": [
    {
      "id": "550e8400-...",
      "name": "Oatmeal",
      "meal_type": "breakfast",
      "calories": 350,
      "protein_g": 12,
      "carbs_g": 60,
      "fat_g": 6
    }
  ],
  "totals": {
    "calories": 350,
    "protein_g": 12,
    "carbs_g": 60,
    "fat_g": 6
  }
}
```

#### `GET /meals/weekly-plan/{user_id}`
Returns all meal logs grouped by day for the current week (Mon–Sun).

#### `POST /meals`
Logs a new meal.

```json
// Request body
{
  "user_id": "user_abc",
  "name": "Grilled chicken",
  "meal_type": "lunch",
  "date": "2026-03-28",      // optional, defaults to today
  "calories": 420,
  "protein_g": 55,
  "carbs_g": 10,
  "fat_g": 18,
  "notes": "with salad"
}
// Response 201
{ "id": "550e8400-...", ... }
```

#### `PUT /meals/{meal_id}`
Updates an existing meal log.

#### `DELETE /meals/{meal_id}`
Deletes a meal log.

### Weekly Plan Endpoints

#### `GET /plans/{user_id}`
Returns all weekly meal plans for a user, most recent first.

#### `POST /plans`
Creates a new weekly meal plan.

### Utility Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness probe `{"status": "healthy"}` |
| `GET /ready` | Readiness probe with db status |
| `GET /` | Service info (name, version) |
| `GET /docs` | Swagger UI |
| `GET /redoc` | ReDoc |

---

## 5. Artemis Integration (Contract v1.0)

All Artemis endpoints live under the `/artemis` prefix and are implemented in
`routers/artemis.py`. The contract is **fully implemented** as of March 2026.

### Auth in Artemis Mode

Artemis tokens are accepted via the `Authorization: Bearer <token>` header.
All `/artemis/*` endpoints (except `/manifest`) require a valid token.

Token validation flow:
1. Peek at `iss` claim without verifying signature
2. If `iss == "artemis-auth"`, fetch public key from `ARTEMIS_AUTH_URL/auth/public-key`
3. Verify with RS256 if public key is available; fall back to unverified claims in dev
4. Extract `sub` as `user_id` for all queries

```bash
# Environment variable
ARTEMIS_AUTH_URL=http://localhost:8090   # default
```

### `GET /artemis/manifest`

Returns the module's capability declaration. No auth required.

The manifest declares:
- **Widgets:** `todays_nutrition` (medium), `weekly_calories` (small)
- **Quick actions:** `log_meal`
- **Data provided:** `daily_calories` (permission: `nutrition.calories.read`)
- **Agent tools:** `get_todays_meals`, `log_meal`, `get_weekly_nutrition`

### `GET /artemis/widgets/{widget_id}`

| Widget ID | Data Returned |
|-----------|--------------|
| `todays_nutrition` | `date`, `total_calories`, `total_protein_g`, `total_carbs_g`, `total_fat_g`, `meal_count` |
| `weekly_calories` | `week_start`, 7-day array of `{date, calories}`, `average_calories` |

### `POST /artemis/agent/{tool_id}` (and `GET` for read-only tools)

| Tool ID | Method | Required params | What it does |
|---------|--------|-----------------|--------------|
| `get_todays_meals` | GET or POST | `date` (optional) | Returns meals + totals for a day |
| `log_meal` | POST | `name`, `meal_type` | Logs a meal; `calories`, `protein_g`, `carbs_g`, `fat_g`, `notes` optional |
| `get_weekly_nutrition` | GET or POST | `week_start` (optional) | Returns 7-day nutrition summary |

All tools return:
```json
{ "success": true, "result": { ... }, "message": "..." }
```

### `GET /artemis/data/{data_id}`

| Data ID | Permission Required | Schema |
|---------|--------------------|----|
| `daily_calories` | `nutrition.calories.read` | `date`, `calories`, `protein_g`, `carbs_g`, `fat_g` |

Query params: `?date=YYYY-MM-DD` (defaults to today).

---

## 6. Standalone Auth — Implementation Plan

Currently these services accept any `user_id` without verification. To operate as a
standalone app, meal-planner needs to issue and validate its own JWTs.

**Recommended approach (when implementing):**

1. Add a `users` table (or defer to a shared auth service)
2. Expose `POST /auth/login` and `POST /auth/register`
3. Issue HS256 or RS256 JWTs with `iss: "meal-planner"`
4. Add `require_standalone_token` dependency alongside the existing `require_token`
5. Update all standalone API endpoints (§4) to require this token
6. In `require_token` (artemis router), also accept `iss: "meal-planner"` tokens

Until then, standalone endpoints are unauthenticated. **Do not expose the service
publicly without auth.**

---

## 7. Local Development

### Setup

```bash
cd services/meal-planner
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create the SQLite dev database
DATABASE_URL=sqlite:///meal-planner.db python migrate_db.py

# Run the server
DATABASE_URL=sqlite:///meal-planner.db uvicorn main:app --reload --port 8010
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///app.db` | Database connection string |
| `ARTEMIS_AUTH_URL` | `http://localhost:8090` | Artemis auth service URL for public key fetch |

### Running with All Services

To run the full local stack, all services must use the same `DATABASE_URL` pointing
to separate databases (each service owns its own schema):

```bash
# Recommended: use separate SQLite files per service
DATABASE_URL=sqlite:///./data/meal-planner.db uvicorn main:app --reload --port 8010
```

---

## 8. Testing

```bash
source .venv/bin/activate
pytest tests/ -v
```

### Test Strategy

- **`tests/test_artemis.py`** — Integration tests for all Artemis contract endpoints.
  Uses a temp SQLite file, a HS256 test token with `iss: "artemis-auth"` (exploits
  dev fallback when auth service is unreachable), and the full FastAPI `TestClient`.

- **`tests/test_meals.py`** — Unit/integration tests for standalone meal endpoints.

Tests are isolated per module: each test file creates its own SQLite database
via `tempfile.mktemp()` and tears it down on fixture cleanup.

### Adding New Tests

Follow the existing pattern in `test_artemis.py`:
1. Use `scope="module"` fixture to share the TestClient across tests
2. Use the HS256 test token `AUTH` header
3. Seed data at the fixture level, not inside individual tests
4. Assert response shapes, not just status codes

---

## 9. Deployment

```dockerfile
# Dockerfile — already present
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010"]
```

**Production:**
- Deployed to AWS ECS Fargate via `rummel-tech/infrastructure`
- Production URL: `https://api.rummeltech.com/meal-planner`
- Database: Amazon RDS PostgreSQL
- Env vars injected via AWS Secrets Manager

---

## 10. Feature Roadmap

### Standalone Enhancements

| Priority | Feature | Notes |
|----------|---------|-------|
| High | Standalone JWT auth (§6) | Required before any public exposure |
| High | `PUT /meals/{id}` and `DELETE /meals/{id}` | CRUD is incomplete |
| Medium | Recipe library | `recipes` table: ingredients, macros, prep time |
| Medium | Meal templates | Re-use common meals without re-entering macros |
| Medium | Nutrition goals | Daily calorie and macro targets per user |
| Low | Shopping list generation | Derive from weekly plan + recipe ingredients |
| Low | Barcode scanning | Integrate with nutrition API for auto-fill |

### Artemis Enhancements

| Priority | Feature | Notes |
|----------|---------|-------|
| High | `GET /artemis/summary` | Natural language daily nutrition summary for AI briefings |
| High | `GET /artemis/calendar` | Planned meals as calendar events (meal_type + time) |
| Medium | `consumes_data: calories_burned` | Accept workout-planner calorie burn to compute net calories |
| Medium | `provides_data: macros` | Expose daily macro breakdown (protein_g, carbs_g, fat_g) |
| Medium | `provides_data: meal_schedule` | Expose planned meals for Artemis calendar view |
| Low | `GET /artemis/notifications` | Remind user when a meal_type hasn't been logged by late morning |

### Schema Evolutions Needed

When implementing recipes:
```sql
CREATE TABLE recipes (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    calories_per_serving INTEGER,
    protein_g_per_serving INTEGER,
    carbs_g_per_serving INTEGER,
    fat_g_per_serving INTEGER,
    prep_minutes INTEGER,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 11. Cross-Module Data

### Provides

| Data ID | Permission | Used By |
|---------|-----------|---------|
| `daily_calories` | `nutrition.calories.read` | workout-planner (adjust burn targets) |
| `macros` *(planned)* | `nutrition.macros.read` | artemis-agent |
| `meal_schedule` *(planned)* | `nutrition.schedule.read` | artemis-calendar |

### Consumes

| Provider | Data ID | Use Case |
|----------|---------|---------|
| workout-planner | `calories_burned` | Display net calories (intake − burn) |

Cross-module consumption is optional. If the workout-planner service is unavailable,
meal-planner should degrade gracefully and omit the net-calories calculation.

---

## 12. Known Issues & Tech Debt

| Issue | Severity | Notes |
|-------|----------|-------|
| No standalone auth | High | Users can query any user's data by ID |
| `weekly_meal_plans` table not used by Artemis router | Low | Agent tools operate on `meals` directly |
| `migrate_db.py` uses PostgreSQL syntax (`UUID`, `NOW()`) | Medium | Doesn't run against SQLite; tests create schema inline |
| Duplicate `NOW()` in SQL | Low | Should use `CURRENT_TIMESTAMP` for cross-DB compat |
| `updated_at` not auto-updated on row changes | Low | Would need a trigger or ORM |

---

*Specification last updated: March 2026*
*Artemis contract version implemented: 1.0*
