# Home Manager — Module Specification

> **Scope:** This document covers the `services/home-manager` FastAPI backend.
> For the Flutter frontend, see `home-manager/` at the monorepo root.
> For the platform-wide integration contract, see `rummel-tech/resources/ARTEMIS_MODULE_CONTRACT.md`.

---

## 1. Purpose & Domain

Home Manager organises household tasks, tracks home assets and their condition,
and supports project planning for home improvements. It is designed to operate as
a fully independent application and as a module within the Artemis Personal OS.

**Core responsibilities:**
- Create, assign, and complete household tasks with priority and category
- Track physical home assets (appliances, tools, systems) with condition records
- Support multi-room organisation and recurring task scheduling
- Record goals for home improvement projects

**Out of scope for this service:**
- Financial tracking of home costs — that would belong to a finance module
- Document/warranty storage (future feature)
- Smart home device integration (future feature)

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
| Port | **8020** |

---

## 3. Database Schema

### `tasks`

Central table. One row per household task.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID / TEXT | Primary key |
| `user_id` | VARCHAR(255) | JWT `sub` claim |
| `title` | VARCHAR(255) | Required |
| `description` | TEXT | Optional detail |
| `status` | VARCHAR(50) | `open`, `in_progress`, `done` |
| `priority` | VARCHAR(50) | `low`, `medium`, `high` |
| `category` | VARCHAR(100) | `chores`, `cleaning`, `maintenance`, `errands`, etc. |
| `due_date` | DATE / TEXT | ISO `YYYY-MM-DD`, nullable |
| `estimated_minutes` | INTEGER | Nullable |
| `tags` | TEXT | Stored as serialised list; parse on read |
| `context` | JSONB / TEXT | Service-specific metadata |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Indexes:** `user_id`, `status`, `due_date`

> **Status values:** The Artemis router uses lowercase `open`, `in_progress`, `done`.
> The common `TaskStatus` enum uses `pending`, `in_progress`, `completed`, `cancelled`,
> `on_hold`. There is a mismatch between the two — the Artemis router operates directly
> on the `tasks` table with its own simpler status set. Align these in a future migration.

### `goals`

Home improvement goals (e.g. "renovate kitchen by Q4").

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID / TEXT | Primary key |
| `user_id` | VARCHAR(255) | |
| `title` | VARCHAR(255) | |
| `description` | TEXT | |
| `category` | VARCHAR(100) | `renovation`, `maintenance`, `organisation`, etc. |
| `target_value` | REAL | Numeric goal (e.g. budget in $) |
| `target_unit` | VARCHAR(50) | Unit of target_value (e.g. `dollars`) |
| `target_date` | DATE / TEXT | Target completion date |
| `current_value` | REAL | Progress toward target |
| `is_active` | BOOLEAN | |
| `progress_percentage` | INTEGER | 0–100 |
| `notes` | TEXT | |
| `context` | JSONB / TEXT | |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Indexes:** `user_id`, `is_active`

### `assets`

Physical home assets (appliances, tools, HVAC systems, furniture, etc.).

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID / TEXT | Primary key |
| `user_id` | VARCHAR(255) | |
| `name` | VARCHAR(255) | e.g. "Bosch Dishwasher" |
| `description` | TEXT | |
| `asset_type` | VARCHAR(100) | `appliance`, `tool`, `system`, `furniture`, etc. |
| `category` | VARCHAR(100) | Room or functional group |
| `manufacturer` | VARCHAR(100) | |
| `model_number` | VARCHAR(100) | |
| `serial_number` | VARCHAR(100) | |
| `purchase_date` | DATE / TEXT | |
| `purchase_price` | REAL | |
| `condition` | VARCHAR(50) | `excellent`, `good`, `fair`, `poor`, `needs_repair` |
| `location` | VARCHAR(100) | Room or location string |
| `notes` | TEXT | |
| `context` | JSONB / TEXT | |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Indexes:** `user_id`, `asset_type`, `category`

### Additional Tables (in `migrate_db.py`)

| Table | Purpose |
|-------|---------|
| `projects` | Multi-task home improvement projects (title, status, budget, timeline) |
| `project_items` | Tasks or materials linked to a project |
| `materials` | Inventory of materials for projects (quantity, cost, supplier) |
| `resources` | Reference URLs, manuals, warranty documents |

### Running Migrations

```bash
# Against local SQLite (dev)
DATABASE_URL=sqlite:///home-manager.db python migrate_db.py

# Against PostgreSQL (prod)
DATABASE_URL=postgresql://user:pass@host/dbname python migrate_db.py
```

---

## 4. Standalone API

The standalone API provides CRUD access to all entities.

> **Auth gap:** Endpoints currently accept any `user_id` without token verification.
> See §6 for the standalone auth implementation plan.

### Task Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/tasks/{user_id}` | List all tasks for user (supports `status` and `priority` filters) |
| `POST` | `/tasks` | Create a task |
| `GET` | `/tasks/{user_id}/{task_id}` | Get a specific task |
| `PUT` | `/tasks/{user_id}/{task_id}` | Update a task |
| `DELETE` | `/tasks/{user_id}/{task_id}` | Delete a task |
| `GET` | `/tasks/weekly/{user_id}` | Legacy endpoint — all tasks for this week |

#### Create Task

```json
// POST /tasks
// Body (TaskCreate model)
{
  "user_id": "user_abc",
  "title": "Fix leaky bathroom faucet",
  "description": "Hot water tap drips overnight",
  "status": "open",
  "priority": "high",
  "category": "maintenance",
  "due_date": "2026-04-05",
  "estimated_minutes": 60
}
// Response 201 — full Task object with generated id, timestamps
```

#### Update Task

```json
// PUT /tasks/{user_id}/{task_id}
// Body (TaskUpdate model — all fields optional)
{
  "status": "done",
  "priority": "medium"
}
```

### Goal Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/goals/{user_id}` | List all goals for user |
| `POST` | `/goals` | Create a goal |
| `GET` | `/goals/{user_id}/{goal_id}` | Get a specific goal |
| `GET` | `/goals/list/{user_id}` | Legacy list endpoint |

### Asset Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/assets/{user_id}` | List assets; optional `asset_type` filter |
| `POST` | `/assets` | Create an asset |

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

Same pattern as all other modules: accepts `Authorization: Bearer <token>` where
the token has `iss == "artemis-auth"`. See §6 of `ARTEMIS_MODULE_CONTRACT.md`
for the full auth flow.

```bash
ARTEMIS_AUTH_URL=http://localhost:8090   # default
```

### `GET /artemis/manifest`

No auth required. Returns the module capability declaration.

The manifest declares:
- **Widgets:** `open_tasks` (small), `upcoming_tasks` (medium)
- **Quick actions:** `create_task`
- **Data provided:** `open_task_count` (permission: `home.tasks.read`)
- **Agent tools:** `list_tasks`, `create_task`, `complete_task`, `list_assets`

### `GET /artemis/widgets/{widget_id}`

| Widget ID | Data Returned |
|-----------|--------------|
| `open_tasks` | `count`, array of up to 5 open tasks `{id, title, priority, status, due_date}` |
| `upcoming_tasks` | `count`, all tasks due in the next 7 days sorted by `due_date` |

> `upcoming_tasks` uses `date.today() + timedelta(days=7)` for the window end —
> do not revert to `date.replace(day=day+7)` which overflows at end of month.

### `POST/GET /artemis/agent/{tool_id}`

| Tool ID | Method | Required params | What it does |
|---------|--------|-----------------|--------------|
| `list_tasks` | GET or POST | — | Lists tasks; optional `status` and `priority` filters |
| `create_task` | POST | `title` | Creates a task; `description`, `priority`, `category`, `due_date` optional |
| `complete_task` | POST | `task_id` | Sets task status to `done`; returns 404 if not found |
| `list_assets` | GET or POST | — | Lists assets; optional `category` filter |

All tools return:
```json
{ "success": true, "result": { ... }, "message": "..." }
```

### `GET /artemis/data/{data_id}`

| Data ID | Permission Required | Schema |
|---------|--------------------|----|
| `open_task_count` | `home.tasks.read` | `count` (int), `overdue` (int — tasks past due date) |

---

## 6. Standalone Auth — Implementation Plan

Currently unauthenticated. To operate as a standalone app:

1. Add `users` table or integrate with a shared auth service
2. Expose `POST /auth/register` and `POST /auth/login`
3. Issue JWTs with `iss: "home-manager"` (or defer to shared auth service)
4. Protect all standalone endpoints with `require_standalone_token` dependency
5. In `routers/artemis.py`, the existing `require_token` already handles Artemis JWTs;
   extend it to also accept `iss: "home-manager"` tokens if standalone auth is added

**Priority:** High — do not expose publicly without auth.

---

## 7. Local Development

### Setup

```bash
cd services/home-manager
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create the SQLite dev database
DATABASE_URL=sqlite:///home-manager.db python migrate_db.py

# Run the server
DATABASE_URL=sqlite:///home-manager.db uvicorn main:app --reload --port 8020
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///app.db` | Database connection string |
| `ARTEMIS_AUTH_URL` | `http://localhost:8090` | Artemis auth service URL |

---

## 8. Testing

```bash
source .venv/bin/activate
pytest tests/ -v
```

### Test Strategy

- **`tests/test_artemis.py`** — 15 integration tests covering the full Artemis
  contract: manifest, auth enforcement, both widgets, all 4 agent tools (including
  error cases), and the `open_task_count` data endpoint.

- **`tests/test_tasks.py`** — Tests for the standalone task API.

Each test module creates a fresh SQLite temp database via `tempfile.mktemp()` and
deletes it on teardown. The `client` fixture has `scope="module"` so all tests in
a file share one DB — test order matters for state-building tests (e.g. create then
complete a task).

### Adding New Tests

```python
# Pattern — add to test_artemis.py
def test_my_new_feature(client):
    r = client.post("/artemis/agent/create_task", headers=AUTH, json={
        "title": "My task",
        "priority": "high",
    })
    assert r.status_code == 200
    assert r.json()["success"] is True
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
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020"]
```

**Production:**
- AWS ECS Fargate via `rummel-tech/infrastructure`
- Production URL: `https://api.rummeltech.com/home-manager`
- Database: Amazon RDS PostgreSQL
- Env vars via AWS Secrets Manager

---

## 10. Feature Roadmap

### Standalone Enhancements

| Priority | Feature | Notes |
|----------|---------|-------|
| High | Standalone JWT auth (§6) | Required before any public exposure |
| High | Recurring task support | `recurrence_rule` (daily/weekly/monthly) on tasks |
| Medium | Projects full implementation | `projects` + `project_items` tables exist; need API endpoints |
| Medium | Task time tracking | `completed_at` column exists; add a `start_task` endpoint |
| Medium | Asset maintenance log | Link `maintenance_records` to assets for service history |
| Low | Room/location hierarchy | Allow grouping assets and tasks by room |
| Low | Warranty & document storage | Link to S3 URLs for PDFs, manuals |
| Low | Contractor tracking | Track who performed services on home assets |

### Artemis Enhancements

| Priority | Feature | Notes |
|----------|---------|-------|
| High | `GET /artemis/summary` | "You have 3 open tasks, 1 overdue. Next due: Fix faucet tomorrow." |
| High | `GET /artemis/calendar` | Scheduled tasks as calendar events for Artemis unified view |
| Medium | `provides_data: task_schedule` | All tasks with due dates for Artemis calendar |
| Medium | `provides_data: goals_progress` | Goal completion rates for Artemis agent |
| Medium | `update_task` agent tool | Allow the AI agent to reschedule or re-prioritize tasks |
| Low | `GET /artemis/notifications` | Notify when tasks are overdue or due today |

### Schema Evolutions Needed

Recurring tasks:
```sql
ALTER TABLE tasks ADD COLUMN recurrence_rule VARCHAR(50);  -- daily, weekly, monthly
ALTER TABLE tasks ADD COLUMN recurrence_end_date DATE;
ALTER TABLE tasks ADD COLUMN parent_task_id UUID REFERENCES tasks(id);
```

---

## 11. Cross-Module Data

### Provides

| Data ID | Permission | Description | Used By |
|---------|-----------|-------------|---------|
| `open_task_count` | `home.tasks.read` | Count of open and overdue tasks | artemis-agent |
| `task_schedule` *(planned)* | `home.tasks.read` | Upcoming tasks with due dates | artemis-calendar |
| `goals_progress` *(planned)* | `home.goals.read` | Active goals and completion rates | artemis-agent |

### Consumes

Home Manager has no mandatory cross-module data dependencies. Future options:
- Consume `calories_burned` from workout-planner to suggest rest-day chores
- Consume `weather` from a future weather module to schedule outdoor tasks

---

## 12. Known Issues & Tech Debt

| Issue | Severity | Notes |
|-------|----------|-------|
| No standalone auth | High | All endpoints unauthenticated |
| Task status mismatch | Medium | Artemis router uses `open/in_progress/done`; common model uses `pending/completed` etc. Needs alignment |
| `context` stored as string in SQLite | Medium | `str(context)` on insert, not JSON. Pydantic rejects it as non-dict on reads via native API |
| `projects`, `materials`, `resources` tables created but have no API endpoints | Low | Schema exists, implementation pending |
| `list_tasks` GET endpoint ignores query params in some client setups | Low | Use POST with JSON body as workaround for the agent |
| `updated_at` not auto-updated | Low | Needs trigger or ORM-level handling |

---

*Specification last updated: March 2026*
*Artemis contract version implemented: 1.0*
