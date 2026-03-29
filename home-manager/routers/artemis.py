"""Artemis platform integration router for Home Manager.

Implements the Artemis Module Contract v1.0:
  GET  /artemis/manifest
  GET  /artemis/widgets/{widget_id}
  POST /artemis/agent/{tool_id}
  GET  /artemis/data/{data_id}
"""
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from common.database import get_connection, get_cursor, get_database_url, is_sqlite
from routers.auth import TokenData as _TokenData, require_token

USE_SQLITE = is_sqlite(get_database_url())
router = APIRouter(prefix="/artemis", tags=["artemis"])


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

MANIFEST = {
    "module": {
        "id": "home-manager",
        "name": "Home Manager",
        "version": "1.0.0",
        "contract_version": "1.0",
        "description": "Property and household task management",
        "icon": "home",
        "color": "#8b5cf6",
        "standalone_url": "https://rummel-tech.github.io/home-manager/",
        "api_base": "https://api.rummeltech.com/home-manager",
    },
    "capabilities": {
        "auth": {"accepts_artemis_token": True, "standalone_auth": False},
        "dashboard_widgets": [
            {
                "id": "open_tasks",
                "name": "Open Tasks",
                "description": "Current open household tasks",
                "size": "small",
                "data_endpoint": "/artemis/widgets/open_tasks",
                "refresh_seconds": 300,
            },
            {
                "id": "upcoming_tasks",
                "name": "Upcoming Tasks",
                "description": "Tasks due in the next 7 days",
                "size": "medium",
                "data_endpoint": "/artemis/widgets/upcoming_tasks",
                "refresh_seconds": 3600,
            },
        ],
        "quick_actions": [
            {
                "id": "create_task",
                "label": "Add Task",
                "icon": "add_circle",
                "endpoint": "/artemis/agent/create_task",
                "method": "POST",
            },
        ],
        "provides_data": [
            {
                "id": "open_task_count",
                "name": "Open Task Count",
                "description": "Number of open household tasks",
                "endpoint": "/artemis/data/open_task_count",
                "schema": {"count": "number", "overdue": "number"},
                "requires_permission": "home.tasks.read",
            },
        ],
        "agent_tools": [
            {
                "id": "list_tasks",
                "description": "List open household tasks",
                "endpoint": "/artemis/agent/list_tasks",
                "method": "GET",
                "parameters": {
                    "status": {"type": "string", "description": "Filter by status (open, in_progress, done)", "required": False},
                    "priority": {"type": "string", "description": "Filter by priority (low, medium, high)", "required": False},
                },
            },
            {
                "id": "create_task",
                "description": "Create a new household task",
                "endpoint": "/artemis/agent/create_task",
                "method": "POST",
                "parameters": {
                    "title": {"type": "string", "required": True},
                    "description": {"type": "string", "required": False},
                    "priority": {"type": "string", "description": "low, medium, or high", "required": False},
                    "category": {"type": "string", "required": False},
                    "due_date": {"type": "string", "description": "ISO date", "required": False},
                },
            },
            {
                "id": "complete_task",
                "description": "Mark a household task as complete",
                "endpoint": "/artemis/agent/complete_task",
                "method": "POST",
                "parameters": {
                    "task_id": {"type": "string", "required": True},
                },
            },
            {
                "id": "list_assets",
                "description": "List home assets and their condition",
                "endpoint": "/artemis/agent/list_assets",
                "method": "GET",
                "parameters": {
                    "category": {"type": "string", "required": False},
                },
            },
        ],
        "optional_endpoints": [
            {
                "path": "/artemis/summary",
                "description": "Natural language task and household summary for AI briefings",
            },
            {
                "path": "/artemis/calendar",
                "description": "Upcoming calendar events for the next 14 days",
            },
        ],
    },
}


@router.get("/manifest")
def get_manifest() -> dict:
    return MANIFEST


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(sql: str, params: tuple) -> list[dict]:
    with get_connection() as conn:
        cur = get_cursor(conn, dict_cursor=not USE_SQLITE)
        if USE_SQLITE:
            sql = sql.replace("%s", "?")
        cur.execute(sql, params)
        rows = cur.fetchall()
        if USE_SQLITE:
            return [dict(zip([d[0] for d in cur.description], row)) for row in rows]
        return [dict(row) for row in rows]



# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

@router.get("/widgets/{widget_id}")
def get_widget(widget_id: str, token: _TokenData = Depends(require_token)) -> dict:
    now = datetime.now(timezone.utc).isoformat() + "Z"
    user_id = token.user_id

    if widget_id == "open_tasks":
        rows = _q("SELECT id, title, priority, status, due_date FROM tasks WHERE user_id = %s AND status != 'done' ORDER BY due_date ASC LIMIT 5", (user_id,))
        tasks = []
        for r in rows:
            tasks.append(r)
        return {
            "widget_id": "open_tasks",
            "data": {"count": len(rows), "tasks": tasks},
            "last_updated": now,
        }

    if widget_id == "upcoming_tasks":
        today = str(date.today())
        week_end = str(date.today() + timedelta(days=7))
        rows = _q(
            "SELECT id, title, priority, status, due_date, category FROM tasks WHERE user_id = %s AND due_date >= %s AND due_date <= %s AND status != 'done' ORDER BY due_date ASC",
            (user_id, today, week_end),
        )
        tasks = []
        for r in rows:
            tasks.append(r)
        return {
            "widget_id": "upcoming_tasks",
            "data": {"tasks": tasks, "count": len(tasks)},
            "last_updated": now,
        }

    raise HTTPException(status_code=404, detail=f"Unknown widget: {widget_id}")


# ---------------------------------------------------------------------------
# Agent tools
# ---------------------------------------------------------------------------

@router.get("/agent/list_tasks")
@router.post("/agent/list_tasks")
def agent_list_tasks(
    task_status: Optional[str] = None,
    priority: Optional[str] = None,
    body: Optional[dict] = None,
    token: _TokenData = Depends(require_token),
) -> dict:
    params_body = body or {}
    filter_status = task_status or params_body.get("status")
    filter_priority = priority or params_body.get("priority")

    sql = "SELECT id, title, priority, status, category, due_date FROM tasks WHERE user_id = %s"
    params: list = [token.user_id]
    if filter_status:
        sql += " AND status = %s"
        params.append(filter_status)
    if filter_priority:
        sql += " AND priority = %s"
        params.append(filter_priority)
    sql += " ORDER BY due_date ASC LIMIT 20"

    rows = _q(sql, tuple(params))
    tasks = []
    for r in rows:
        tasks.append(r)
    return {"success": True, "result": {"tasks": tasks, "count": len(tasks)}}


@router.post("/agent/create_task")
def agent_create_task(body: dict, token: _TokenData = Depends(require_token)) -> dict:
    title = body.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    task_id = str(uuid.uuid4())
    with get_connection() as conn:
        cur = get_cursor(conn, dict_cursor=not USE_SQLITE)
        sql = """INSERT INTO tasks (id, user_id, title, description, status, priority, category, due_date)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""" if USE_SQLITE else \
              """INSERT INTO tasks (id, user_id, title, description, status, priority, category, due_date)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
        cur.execute(sql, (
            task_id, token.user_id, title,
            body.get("description", ""),
            "open",
            body.get("priority", "medium"),
            body.get("category", ""),
            body.get("due_date"),
        ))
        conn.commit()

    return {
        "success": True,
        "result": {"task_id": task_id, "title": title},
        "message": f"Created task: {title}",
    }


@router.post("/agent/complete_task")
def agent_complete_task(body: dict, token: _TokenData = Depends(require_token)) -> dict:
    task_id = body.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id is required")

    with get_connection() as conn:
        cur = get_cursor(conn, dict_cursor=not USE_SQLITE)
        sql = "UPDATE tasks SET status = 'done' WHERE id = %s AND user_id = %s"
        if USE_SQLITE:
            sql = sql.replace("%s", "?")
        cur.execute(sql, (task_id, token.user_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        conn.commit()

    return {"success": True, "result": {"task_id": task_id, "status": "done"}, "message": "Task marked as complete"}


@router.get("/agent/list_assets")
@router.post("/agent/list_assets")
def agent_list_assets(
    category: Optional[str] = None,
    body: Optional[dict] = None,
    token: _TokenData = Depends(require_token),
) -> dict:
    filter_cat = category or (body or {}).get("category")
    sql = "SELECT id, name, asset_type, category, condition, location FROM assets WHERE user_id = %s"
    params: list = [token.user_id]
    if filter_cat:
        sql += " AND category = %s"
        params.append(filter_cat)
    sql += " ORDER BY name LIMIT 20"

    rows = _q(sql, tuple(params))
    assets = []
    assets = list(rows)
    return {"success": True, "result": {"assets": assets, "count": len(assets)}}


# ---------------------------------------------------------------------------
# Cross-module data
# ---------------------------------------------------------------------------

@router.get("/data/{data_id}")
def get_shared_data(data_id: str, token: _TokenData = Depends(require_token)) -> dict:
    if data_id == "open_task_count":
        rows = _q("SELECT COUNT(*) as cnt FROM tasks WHERE user_id = %s AND status != 'done'", (token.user_id,))
        total = rows[0]["cnt"] if rows else 0

        today = str(date.today())
        overdue_rows = _q(
            "SELECT COUNT(*) as cnt FROM tasks WHERE user_id = %s AND status != 'done' AND due_date < %s",
            (token.user_id, today),
        )
        overdue = overdue_rows[0]["cnt"] if overdue_rows else 0
        return {"data_id": "open_task_count", "data": {"count": total, "overdue": overdue}}

    raise HTTPException(status_code=404, detail=f"Unknown data_id: {data_id}")


# ---------------------------------------------------------------------------
# Summary (optional contract endpoint)
# ---------------------------------------------------------------------------

@router.get("/summary")
def get_summary(token: _TokenData = Depends(require_token)) -> dict:
    """Return a natural language task summary for AI briefings."""
    today = str(date.today())

    open_rows = _q("SELECT COUNT(*) as cnt FROM tasks WHERE user_id = %s AND status = 'open'", (token.user_id,))
    in_progress_rows = _q("SELECT COUNT(*) as cnt FROM tasks WHERE user_id = %s AND status = 'in_progress'", (token.user_id,))
    overdue_rows = _q(
        "SELECT COUNT(*) as cnt FROM tasks WHERE user_id = %s AND status != 'done' AND due_date < %s",
        (token.user_id, today),
    )
    next_rows = _q(
        "SELECT title, due_date, priority FROM tasks WHERE user_id = %s AND status != 'done' AND due_date >= %s ORDER BY due_date ASC LIMIT 1",
        (token.user_id, today),
    )

    open_count = open_rows[0]["cnt"] if open_rows else 0
    in_progress_count = in_progress_rows[0]["cnt"] if in_progress_rows else 0
    overdue_count = overdue_rows[0]["cnt"] if overdue_rows else 0
    next_task = next_rows[0] if next_rows else None

    parts = []
    total_active = open_count + in_progress_count
    if total_active == 0:
        parts.append("No open tasks.")
    else:
        parts.append(f"{total_active} active task{'s' if total_active != 1 else ''} ({open_count} open, {in_progress_count} in progress).")
    if overdue_count:
        parts.append(f"{overdue_count} overdue.")
    if next_task:
        parts.append(f"Next due: {next_task['title']} ({next_task['due_date']}).")

    return {
        "module_id": "home-manager",
        "summary": " ".join(parts),
        "data": {
            "open_tasks": open_count,
            "in_progress_tasks": in_progress_count,
            "overdue_tasks": overdue_count,
            "next_due_task": dict(next_task) if next_task else None,
        },
    }


# ---------------------------------------------------------------------------
# Calendar (optional contract endpoint)
# ---------------------------------------------------------------------------

@router.get("/calendar")
def get_calendar(token: _TokenData = Depends(require_token)) -> dict:
    """Return upcoming task events due in the next 14 days."""
    today = datetime.today().date()
    window_end = today + timedelta(days=14)

    rows = _q(
        "SELECT id, title, due_date, priority, description FROM tasks "
        "WHERE user_id = %s AND due_date >= %s AND due_date <= %s AND status != 'done' "
        "ORDER BY due_date ASC LIMIT 20",
        (token.user_id, str(today), str(window_end)),
    )

    events = []
    for row in rows:
        events.append({
            "id": str(row.get("id", uuid.uuid4())),
            "title": row.get("title") or "Task",
            "date": str(row["due_date"]),
            "type": "task",
            "priority": row.get("priority") or "medium",
            "notes": row.get("description") or None,
        })

    return {
        "module_id": "home-manager",
        "events": events,
        "window_days": 14,
    }
