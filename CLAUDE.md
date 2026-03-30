# CLAUDE.md — Backend Services

This file provides conventions for all services in `services/`.

## Date Handling Convention

**Rule:** Always use local calendar date for date-only fields. Always use UTC for timestamps.

| Field type | Function to use | Storage format |
|------------|----------------|----------------|
| Date-only (meals, tasks, workouts) | `datetime.today().date()` | `YYYY-MM-DD` |
| Timestamps (created_at, updated_at, events) | `datetime.now(timezone.utc)` | ISO 8601 with UTC offset |

**Never mix** `datetime.now(timezone.utc).date()` with `date.today()` for the same field.
`datetime.now(timezone.utc).date()` returns the UTC calendar date, which is wrong for users
west of UTC (a meal logged at 11pm local time would appear on the next day).

**Correct:**
```python
# Date-only field
meal_date = str(datetime.today().date())      # "2026-03-28"
due_date = str(datetime.today().date())

# Timestamp field
created_at = datetime.now(timezone.utc).isoformat()   # "2026-03-28T23:00:00+00:00"
```

## SQLite / PostgreSQL Dual-Mode

All services support both SQLite (dev/test) and PostgreSQL (production).

```python
USE_SQLITE = is_sqlite(get_database_url())
```

- Use `adapt_query(sql, USE_SQLITE)` to convert `%s` → `?` and strip `RETURNING *`
- Use `get_cursor(conn)` — it correctly detects SQLite vs PostgreSQL via `isinstance`
- Use `dict_from_row(row, USE_SQLITE)` to convert rows to dicts

## JSON Fields in SQLite

SQLite has no native JSON type. Fields typed `JSONB` in PostgreSQL are stored as TEXT in SQLite.

**On insert:**
```python
json.dumps(obj.context or {})   # NOT str(obj.context)
```

**On read (before Pydantic construction):**
```python
if USE_SQLITE and isinstance(row_dict.get("context"), str):
    row_dict["context"] = json.loads(row_dict["context"])
```

## Artemis Token Auth Pattern

Every module's `routers/artemis.py` must follow this pattern:

```python
_artemis_public_key: Optional[str] = None
_artemis_public_key_fetched_at: float = 0.0
_KEY_CACHE_TTL = 86400  # 24 hours

def _fetch_artemis_public_key() -> Optional[str]:
    global _artemis_public_key, _artemis_public_key_fetched_at
    now = time.time()
    if _artemis_public_key and (now - _artemis_public_key_fetched_at) < _KEY_CACHE_TTL:
        return _artemis_public_key
    # ... fetch and cache ...

def require_token(...):
    # ...
    pub_key = _fetch_artemis_public_key()
    if pub_key:
        # verify RS256
    else:
        # dev fallback — ONLY outside production
        if os.getenv("ENVIRONMENT", "development") != "production":
            return _TokenData(...)
        raise HTTPException(503, "Auth service unavailable")
```

## Task Status Values

The canonical task status values (standardised March 2026) are:

| Value | Meaning |
|-------|---------|
| `open` | Not started |
| `in_progress` | Active |
| `done` | Completed |

Use `TaskStatus.OPEN`, `TaskStatus.IN_PROGRESS`, `TaskStatus.DONE` from `common.models`.
Legacy values (`pending`, `completed`, `cancelled`, `on_hold`) are kept for backward
compat but should not be used in new code.

## Port Assignments

| Service | Port |
|---------|------|
| workout-planner | 8000 |
| meal-planner | 8010 |
| home-manager | 8020 |
| vehicle-manager | 8030 |
| work-planner | 8040 |
| artemis (platform) | 8080 |
| auth | 8090 |
