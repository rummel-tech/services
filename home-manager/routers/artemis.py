"""Artemis platform integration router for Home Manager.

Implements the Artemis Module Contract v1.0:
  GET  /artemis/manifest
  GET  /artemis/widgets/{widget_id}
  POST /artemis/agent/{tool_id}
  GET  /artemis/data/{data_id}
"""
import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from common.database import adapt_query, get_connection, get_cursor, get_database_url, is_sqlite

USE_SQLITE = is_sqlite(get_database_url())
router = APIRouter(prefix="/artemis", tags=["artemis"])

ARTEMIS_AUTH_URL = os.getenv("ARTEMIS_AUTH_URL", "http://localhost:8090")
_artemis_public_key: Optional[str] = None
_artemis_public_key_fetched_at: float = 0.0
_KEY_CACHE_TTL = 86400  # 24 hours


def _fetch_artemis_public_key() -> Optional[str]:
    global _artemis_public_key, _artemis_public_key_fetched_at
    now = time.time()
    if _artemis_public_key and (now - _artemis_public_key_fetched_at) < _KEY_CACHE_TTL:
        return _artemis_public_key
    try:
        r = httpx.get(f"{ARTEMIS_AUTH_URL}/auth/public-key", timeout=3.0)
        if r.status_code == 200:
            _artemis_public_key = r.json()["public_key"]
            _artemis_public_key_fetched_at = now
            return _artemis_public_key
    except Exception:
        pass
    return None


class _TokenData(BaseModel):
    user_id: str
    email: str = ""


def require_token(authorization: Optional[str] = Header(None)) -> _TokenData:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    raw = authorization.split(" ", 1)[1]
    try:
        unverified = jwt.get_unverified_claims(raw)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if unverified.get("iss") == "artemis-auth":
        pub_key = _fetch_artemis_public_key()
        if pub_key:
            try:
                payload = jwt.decode(raw, pub_key, algorithms=["RS256"], issuer="artemis-auth")
                return _TokenData(user_id=payload["sub"], email=payload.get("email", ""))
            except JWTError as e:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
        # Dev fallback: auth service not running — only permitted outside production
        if os.getenv("ENVIRONMENT", "development") != "production":
            return _TokenData(user_id=unverified.get("sub", "dev-user"), email=unverified.get("email", ""))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service unavailable")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported token issuer")


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



def _row_to_dict(row) -> dict:
    if hasattr(row, "keys"):
        return dict(row)
    # sqlite3.Row supports index access; fall back to column-ordered dict
    return {k: row[i] for i, k in enumerate(row.description)} if hasattr(row, "description") else {}


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
