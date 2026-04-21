"""Async task queue built on FastAPI BackgroundTasks + a persistent jobs table.

Usage in a router:
    from fastapi import BackgroundTasks
    from common.tasks import enqueue, task

    @task("send_weekly_report")
    async def send_weekly_report(user_id: str) -> dict:
        # long-running work here
        return {"emails_sent": 1}

    @router.post("/trigger-report")
    async def trigger(user_id: str, bg: BackgroundTasks = Depends()):
        job_id = enqueue(bg, send_weekly_report, user_id=user_id)
        return {"job_id": job_id}

    @router.get("/jobs/{job_id}")
    async def job_status(job_id: str):
        return get_job(job_id)

The `jobs` table must exist in the service's database. Call `init_jobs_table()` in the
service startup hook, or include the CREATE TABLE in the service's Alembic migration.
"""
import asyncio
import functools
import json
import logging
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import BackgroundTasks

from common.database import get_connection, adapt_query, dict_from_row, is_sqlite, get_database_url

log = logging.getLogger("common.tasks")

USE_SQLITE = is_sqlite(get_database_url())

JOBS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | running | done | failed
    payload TEXT NOT NULL DEFAULT '{}',
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
)
"""

JOBS_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"


def init_jobs_table() -> None:
    """Create the jobs table if it doesn't exist. Call from service startup."""
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(JOBS_TABLE_SQL)
            cur.execute(JOBS_INDEX_SQL)
            conn.commit()
    except Exception as e:
        log.warning("jobs_table_init_failed: %s", e)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_job(job_id: str, name: str, payload: dict) -> None:
    q = adapt_query(
        "INSERT INTO jobs (id, name, status, payload, created_at) VALUES (%s, %s, %s, %s, %s)",
        USE_SQLITE,
    )
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(q, (job_id, name, "pending", json.dumps(payload), _now()))


def _update_job(job_id: str, status: str, result: Any = None, error: str = None) -> None:
    finished = _now() if status in ("done", "failed") else None
    started = _now() if status == "running" else None

    if status == "running":
        q = adapt_query(
            "UPDATE jobs SET status=%s, started_at=%s WHERE id=%s",
            USE_SQLITE,
        )
        with get_connection() as conn:
            conn.cursor().execute(q, (status, started, job_id))
    else:
        q = adapt_query(
            "UPDATE jobs SET status=%s, result=%s, error=%s, finished_at=%s WHERE id=%s",
            USE_SQLITE,
        )
        with get_connection() as conn:
            conn.cursor().execute(
                q,
                (
                    status,
                    json.dumps(result) if result is not None else None,
                    error,
                    finished,
                    job_id,
                ),
            )


def get_job(job_id: str) -> Optional[dict]:
    """Fetch a job by ID. Returns None if not found."""
    q = adapt_query("SELECT * FROM jobs WHERE id=%s", USE_SQLITE)
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(q, (job_id,))
        row = cur.fetchone()
    if not row:
        return None
    data = dict_from_row(row)
    if data.get("result"):
        try:
            data["result"] = json.loads(data["result"])
        except (json.JSONDecodeError, TypeError):
            pass
    return data


def task(name: str):
    """Decorator that marks a coroutine as a tracked background task."""
    def decorator(fn: Callable):
        fn._task_name = name

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            return await fn(*args, **kwargs)

        wrapper._task_name = name
        return wrapper

    return decorator


def enqueue(background_tasks: BackgroundTasks, fn: Callable, **kwargs) -> str:
    """Schedule `fn(**kwargs)` as a background task and return the job_id.

    The job is persisted immediately as 'pending' so callers can poll its status.
    """
    job_id = str(uuid.uuid4())
    name = getattr(fn, "_task_name", fn.__name__)
    _create_job(job_id, name, kwargs)

    async def _run():
        _update_job(job_id, "running")
        try:
            if asyncio.iscoroutinefunction(fn):
                result = await fn(**kwargs)
            else:
                result = fn(**kwargs)
            _update_job(job_id, "done", result=result)
        except Exception as exc:
            log.exception("background_task_failed job_id=%s name=%s", job_id, name)
            _update_job(job_id, "failed", error=traceback.format_exc(limit=10))

    background_tasks.add_task(_run)
    return job_id
