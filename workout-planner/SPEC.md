# Workout Planner — Module Specification

> **Scope:** This document covers the `services/workout-planner` FastAPI backend.
> For the Flutter frontend, see `workout-planner/` at the monorepo root.
> For the platform-wide integration contract, see `resources/ARTEMIS_MODULE_CONTRACT.md`.

---

## 1. Purpose & Domain

Workout Planner is an AI-powered fitness coaching service. It tracks workouts, generates
daily and weekly training plans based on readiness, and integrates with Apple HealthKit
for biometric data. It operates as a fully independent application and as a module within
the Artemis Personal OS.

**Core responsibilities:**
- Track workouts across multiple modalities (strength, swim, Murph, general)
- Generate AI-driven daily and weekly training plans
- Score daily readiness from HealthKit biometrics (HRV, resting HR, sleep, RPE, soreness)
- Run an AI coach chat interface (GPT-4 based)
- Manage user fitness goals with progress tracking
- Serve as the reference implementation for the Artemis Module Contract

**Out of scope for this service:**
- Nutrition tracking — that belongs to meal-planner
- General health record storage (beyond workout-adjacent biometrics)
- Payment or subscription management

---

## 2. Technology Stack

| Layer | Technology |
|-------|-----------|
| Framework | Python 3.11+, FastAPI |
| Server | Uvicorn |
| Database (prod) | PostgreSQL 15 |
| Database (dev) | SQLite (`fitness_dev.db`) |
| Auth (standalone) | HS256 JWT, `iss: "workout-planner"` — own `users` table |
| Auth (Artemis mode) | RS256 JWT, `iss: "artemis-auth"` |
| AI coaching | OpenAI GPT-4 via `core/ai_chat_service.py` |
| Caching | Redis (`redis://localhost:6379/0`) |
| Port | **8000** |

---

## 3. Database Schema

### Core Tables

| Table | Purpose |
|-------|---------|
| `users` | Accounts: email, hashed_password, created_at |
| `user_goals` | Fitness goals: type, target_value, target_unit, target_date |
| `goal_plans` | Plans linked to goals |
| `weekly_plans` | `week_start`, `focus`, `plan_json` |
| `daily_plans` | `date`, `plan_json`, `status`, `ai_notes` |
| `workouts` | `name`, `type`, warmup/main/cooldown JSON, notes |
| `chat_sessions` | AI coach sessions |
| `chat_messages` | Individual messages in sessions |

### Health & Biometrics Tables

| Table | Purpose |
|-------|---------|
| `health_samples` | HealthKit raw data: type, value, unit, timestamp, source_app |
| `health_metrics` | Daily metrics: HRV, resting_hr, vo2max, sleep, weight, RPE, soreness, mood |
| `strength_metrics` | Lift, weight, reps, set_number, estimated_1rm, velocity |
| `swim_metrics` | Swimming-specific performance data |

### Running Migrations

```bash
cd services/workout-planner
python migrate_db.py   # SQLite dev
DATABASE_URL=postgresql://... python migrate_db.py   # PostgreSQL
```

---

## 4. Standalone API

This service has its own auth — it issues and validates JWTs independently of the Artemis auth service.

### Auth Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/register` | Register new user |
| `POST` | `/auth/login` | Login, returns JWT |
| `POST` | `/auth/logout` | Logout |
| `GET` | `/auth/me` | Current user profile |
| `POST` | `/auth/google` | Google OAuth |

### Workout Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/workouts/{user_id}` | List workouts |
| `POST` | `/workouts` | Create workout |
| `PUT` | `/workouts/{id}` | Update workout |
| `DELETE` | `/workouts/{id}` | Delete workout |

### Plan Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/daily-plans/{user_id}` | Get daily plan (defaults to today) |
| `POST` | `/daily-plans/generate` | Generate AI daily plan |
| `GET` | `/weekly-plans/{user_id}` | Get weekly plan |
| `POST` | `/weekly-plans/generate` | Generate AI weekly plan |

### Readiness Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/readiness/{user_id}` | Current readiness score (0.0–1.0) |
| `POST` | `/readiness/log` | Log RPE, soreness, mood |

### Health Endpoints (HealthKit)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/health/sync` | Bulk sync HealthKit samples |
| `GET` | `/health/metrics/{user_id}` | Daily health metrics |

### AI Chat

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat` | Send message to AI coach |
| `GET` | `/chat/history/{user_id}` | Conversation history |

### Utility Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness probe |
| `GET /ready` | Readiness probe |
| `GET /` | Service info |
| `GET /docs` | Swagger UI |

---

## 5. Artemis Integration (Contract v1.0)

This is the **reference implementation** of the Artemis Module Contract. Use this service
as the canonical example when implementing the contract in other modules.

### Auth in Artemis Mode

Accepts both standalone tokens (`iss: "workout-planner"`) and Artemis platform tokens
(`iss: "artemis-auth"`). This is the dual-mode pattern all modules should follow.

The `require_token` function in `routers/artemis.py`:
1. Checks `iss` claim
2. If `"artemis-auth"`: fetches public key from `ARTEMIS_AUTH_URL/auth/public-key`, verifies RS256
3. If `"workout-planner"`: verifies with own HS256 secret
4. Dev fallback (non-production only): accepts unverified claims when auth service unreachable

```bash
ARTEMIS_AUTH_URL=http://localhost:8090   # default
```

### `GET /artemis/manifest`

No auth required. Module version: **1.2.0**

Declares:
- **Widgets:** `todays_workout` (medium), `weekly_summary` (large)
- **Quick actions:** `log_workout`, `start_workout`
- **Data provided:** `calories_burned`, `readiness_score`, `workout_schedule`
- **Data consumed:** `daily_calories` (from meal-planner, optional)
- **Agent tools:** `get_todays_workout`, `log_workout`, `schedule_workout`, `get_weekly_summary`

### `GET /artemis/widgets/{widget_id}`

| Widget ID | Data Returned |
|-----------|--------------|
| `todays_workout` | Today's plan: `date`, `workout_type`, `exercises`, `readiness_score`, `estimated_duration` |
| `weekly_summary` | Week overview: `workouts_completed`, `total_minutes`, `streak_days`, `next_workout` |

### `POST/GET /artemis/agent/{tool_id}`

| Tool ID | Method | Required params | What it does |
|---------|--------|-----------------|--------------|
| `get_todays_workout` | GET or POST | — | Returns today's workout plan with readiness-adjusted intensity |
| `log_workout` | POST | `workout_type` | Logs a completed workout; `duration_minutes`, `notes` optional |
| `schedule_workout` | POST | `date`, `workout_type` | Schedules a workout for a future date |
| `get_weekly_summary` | GET or POST | `week_start` (optional) | Returns weekly training summary |

### `GET /artemis/data/{data_id}`

| Data ID | Permission Required | Schema |
|---------|--------------------|--------|
| `calories_burned` | `fitness.calories.read` | `date`, `calories_burned`, `workout_type`, `duration_minutes` |
| `readiness_score` | `fitness.readiness.read` | `date`, `score` (0.0–1.0), `components` (HRV, sleep, etc.) |
| `workout_schedule` | `fitness.schedule.read` | Array of `{date, workout_type, status}` for next 7 days |

---

## 6. Readiness Score

The readiness score drives plan adaptation. Score range: 0.0 (depleted) to 1.0 (peak).

Components:
- **HRV** (heart rate variability) — primary signal
- **Resting heart rate** — secondary signal
- **Sleep duration** — hours vs. baseline
- **Subjective RPE** — previous session perceived exertion
- **Soreness** — self-reported muscle soreness

When `readiness < 0.3`: `DailyPlanGenerator` automatically reduces workout intensity,
swaps high-intensity sessions for recovery work.

---

## 7. Local Development

### Setup

```bash
cd services/workout-planner
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create the SQLite dev database
python migrate_db.py

# Run the server
uvicorn main:app --reload --port 8000
```

The Flutter frontend has a `dev.sh` helper:
```bash
cd workout-planner
./dev.sh status      # check services
./dev.sh hot-reload  # apply changes
./dev.sh logs        # tail output
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///fitness_dev.db` | Database connection string |
| `ARTEMIS_AUTH_URL` | `http://localhost:8090` | Artemis auth service URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL (caching) |
| `OPENAI_API_KEY` | — | Required for AI chat and plan generation |
| `ENVIRONMENT` | `development` | Set to `production` to enforce PostgreSQL |

---

## 8. Testing

```bash
source .venv/bin/activate
pytest tests/ -v
```

### Test Files

| File | Coverage |
|------|---------|
| `test_artemis.py` | Full Artemis contract: manifest, widgets, agent tools, data endpoints |
| `test_auth.py` | Register, login, token validation |
| `test_api.py` | Core API endpoints |
| `test_daily_plans.py` | Plan generation and retrieval |
| `test_readiness.py` | Readiness scoring |
| `test_health.py` | HealthKit sync and metrics |
| `test_chat.py` | AI coach chat |
| `test_integration.py` | End-to-end workflows |
| `locustfile.py` | Load testing scenarios |

---

## 9. Deployment

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Production:**
- AWS ECS Fargate via `rummel-tech/infrastructure`
- Production URL: `https://api.rummeltech.com/workout-planner`
- Database: Amazon RDS PostgreSQL
- Env vars via AWS Secrets Manager
- Redis: AWS ElastiCache

---

## 10. Feature Roadmap

### Standalone Enhancements

| Priority | Feature | Notes |
|----------|---------|-------|
| Medium | Recurring workout schedules | Weekly template with auto-generation |
| Medium | Personal records tracking | PR detection on new strength logs |
| Medium | Body composition tracking | Weight, body fat %, measurements |
| Low | Workout video links | Link exercises to video demonstrations |
| Low | Training block periodization | Multi-week progressive overload planning |

### Artemis Enhancements

| Priority | Feature | Notes |
|----------|---------|-------|
| High | `GET /artemis/summary` | Daily briefing: today's plan + readiness + streak |
| High | `GET /artemis/calendar` | Workout schedule as calendar events |
| Medium | `consumes_data: daily_calories` | Net calorie tracking (intake − burn) from meal-planner |
| Medium | `GET /artemis/notifications` | Alert when rest day needed based on readiness |

---

## 11. Cross-Module Data

### Provides

| Data ID | Permission | Used By |
|---------|-----------|---------|
| `calories_burned` | `fitness.calories.read` | meal-planner (net calories) |
| `readiness_score` | `fitness.readiness.read` | artemis-agent |
| `workout_schedule` | `fitness.schedule.read` | artemis-agent, artemis-calendar |

### Consumes

| Provider | Data ID | Use Case |
|----------|---------|---------|
| meal-planner | `daily_calories` | Display net calories (intake − burn) |

Cross-module consumption is optional. If meal-planner is unavailable, degrade gracefully.

---

## 12. Known Issues & Tech Debt

| Issue | Severity | Notes |
|-------|----------|-------|
| `shared_services` Flutter package missing | Medium | Frontend duplicates auth client + API wrapper |
| Redis required for some features | Low | Services degrade gracefully if Redis down |
| OpenAI dependency | Low | Plan generation and AI chat fail silently without `OPENAI_API_KEY` |
| `daily_plans` and `weekly_plans` use JSON blobs | Low | Not easily queryable; consider normalizing |

---

*Specification last updated: March 2026*
*Artemis contract version implemented: 1.0 (module version 1.2.0)*
