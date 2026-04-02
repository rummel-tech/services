"""
Home Manager API - Property and household management service.
"""

import json
import sys
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from dotenv import load_dotenv

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _load_env() -> None:
    import os
    try:
        load_dotenv(override=False)
        custom_path = os.environ.get("SECRETS_ENV_PATH")
        if custom_path:
            secrets_env = Path(custom_path)
        else:
            repo_root = Path(__file__).resolve().parents[2]
            secrets_env = repo_root / "config" / "secrets" / "local.env"
        if secrets_env.exists():
            load_dotenv(dotenv_path=secrets_env, override=True)
    except Exception:
        pass


_load_env()

from common.aws_secrets import inject_secrets_from_aws
inject_secrets_from_aws()

from fastapi import APIRouter, Depends, HTTPException, status

from common import create_app, ServiceConfig
from common.models import (
    Task, Goal, Asset,
    TaskCreate, TaskUpdate,
    GoalCreate,
    AssetCreate,
    TaskStatus, Priority, AssetCondition,
)
from common.database import (
    get_connection, get_cursor, dict_from_row,
    init_db, close_db, adapt_query, is_sqlite, get_database_url,
)
from core.settings import get_settings
from routers import artemis as artemis_router
from routers.auth import TokenData, require_token

settings = get_settings()

config = ServiceConfig(
    name="home-manager",
    title="Home Manager API",
    version="2.0.0",
    description="Property and household management service with database persistence",
    port=settings.port,
    environment=settings.environment,
    debug=settings.debug,
    log_level=settings.log_level,
    cors_origins=settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins],
    enable_security_headers=True,
    enable_request_logging=True,
    enable_error_handlers=True,
    enable_metrics=True,
    enable_rate_limiting=(settings.environment == "production"),
    redis_enabled=settings.redis_enabled,
    redis_url=settings.redis_url,
    on_startup=[init_db],
    on_shutdown=[close_db],
)

app = create_app(config)
router = APIRouter()

USE_SQLITE = is_sqlite(get_database_url())


def _parse_row(row_dict: dict) -> dict:
    if USE_SQLITE and isinstance(row_dict.get("context"), str):
        try:
            row_dict["context"] = json.loads(row_dict["context"])
        except (json.JSONDecodeError, ValueError):
            row_dict["context"] = {}
    return row_dict


# ============================================================================
# Task Endpoints
# ============================================================================

@router.get("/tasks/{user_id}", response_model=List[Task])
async def list_tasks(user_id: str, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query("SELECT * FROM tasks WHERE user_id = %s ORDER BY created_at DESC", USE_SQLITE)
        cur.execute(query, (user_id,))
        rows = cur.fetchall()
        return [Task(**_parse_row(dict_from_row(row, USE_SQLITE))) for row in rows]


@router.post("/tasks", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(task: TaskCreate, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        cur = get_cursor(conn)
        if USE_SQLITE:
            import uuid
            task_id = str(uuid.uuid4())
            query = """INSERT INTO tasks (id, user_id, title, description, status, priority, category,
                                           due_date, estimated_minutes, tags, context)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            cur.execute(query, (
                task_id, task.user_id, task.title, task.description, task.status.value,
                task.priority.value, task.category, task.due_date, task.estimated_minutes,
                json.dumps(task.tags or []), json.dumps(task.context or {}),
            ))
            cur.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        else:
            query = """INSERT INTO tasks (id, user_id, title, description, status, priority, category,
                                           due_date, estimated_minutes, tags, context)
                       VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING *"""
            cur.execute(query, (
                task.user_id, task.title, task.description, task.status.value,
                task.priority.value, task.category, task.due_date, task.estimated_minutes,
                task.tags, task.context,
            ))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create task")
        return Task(**_parse_row(dict_from_row(row, USE_SQLITE)))


@router.get("/tasks/{user_id}/{task_id}", response_model=Task)
async def get_task(user_id: str, task_id: UUID, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query("SELECT * FROM tasks WHERE id = %s AND user_id = %s", USE_SQLITE)
        cur.execute(query, (str(task_id), user_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return Task(**_parse_row(dict_from_row(row, USE_SQLITE)))


@router.put("/tasks/{user_id}/{task_id}", response_model=Task)
async def update_task(user_id: str, task_id: UUID, task_update: TaskUpdate, token: TokenData = Depends(require_token)):
    updates = {k: v for k, v in task_update.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_parts = []
    values = []
    for key, value in updates.items():
        set_parts.append(f"{key} = {'?' if USE_SQLITE else '%s'}")
        values.append(value.value if isinstance(value, (TaskStatus, Priority)) else value)
    values.extend([str(task_id), user_id])

    with get_connection() as conn:
        cur = get_cursor(conn)
        query = f"UPDATE tasks SET {', '.join(set_parts)}, updated_at = {'CURRENT_TIMESTAMP' if USE_SQLITE else 'NOW()'} WHERE id = {'?' if USE_SQLITE else '%s'} AND user_id = {'?' if USE_SQLITE else '%s'}"
        cur.execute(query, values)
        query = adapt_query("SELECT * FROM tasks WHERE id = %s AND user_id = %s", USE_SQLITE)
        cur.execute(query, (str(task_id), user_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return Task(**_parse_row(dict_from_row(row, USE_SQLITE)))


@router.delete("/tasks/{user_id}/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(user_id: str, task_id: UUID, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query("DELETE FROM tasks WHERE id = %s AND user_id = %s", USE_SQLITE)
        cur.execute(query, (str(task_id), user_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found")


# ============================================================================
# Goal Endpoints
# ============================================================================

@router.get("/goals/{user_id}", response_model=List[Goal])
async def list_goals(user_id: str, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query("SELECT * FROM goals WHERE user_id = %s ORDER BY created_at DESC", USE_SQLITE)
        cur.execute(query, (user_id,))
        rows = cur.fetchall()
        return [Goal(**_parse_row(dict_from_row(row, USE_SQLITE))) for row in rows]


@router.post("/goals", response_model=Goal, status_code=status.HTTP_201_CREATED)
async def create_goal(goal: GoalCreate, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        cur = get_cursor(conn)
        if USE_SQLITE:
            import uuid
            goal_id = str(uuid.uuid4())
            query = """INSERT INTO goals (id, user_id, title, description, category, target_value,
                                          target_unit, target_date, notes, context)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            cur.execute(query, (
                goal_id, goal.user_id, goal.title, goal.description, goal.category,
                goal.target_value, goal.target_unit, goal.target_date, goal.notes,
                json.dumps(goal.context or {}),
            ))
            cur.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
        else:
            query = """INSERT INTO goals (id, user_id, title, description, category, target_value,
                                          target_unit, target_date, notes, context)
                       VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING *"""
            cur.execute(query, (
                goal.user_id, goal.title, goal.description, goal.category,
                goal.target_value, goal.target_unit, goal.target_date, goal.notes, goal.context,
            ))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create goal")
        return Goal(**_parse_row(dict_from_row(row, USE_SQLITE)))


@router.get("/goals/{user_id}/{goal_id}", response_model=Goal)
async def get_goal(user_id: str, goal_id: UUID, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query("SELECT * FROM goals WHERE id = %s AND user_id = %s", USE_SQLITE)
        cur.execute(query, (str(goal_id), user_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Goal not found")
        return Goal(**_parse_row(dict_from_row(row, USE_SQLITE)))


# ============================================================================
# Asset Endpoints
# ============================================================================

@router.get("/assets/{user_id}", response_model=List[Asset])
async def list_assets(user_id: str, asset_type: Optional[str] = None, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        cur = get_cursor(conn)
        if asset_type:
            query = adapt_query("SELECT * FROM assets WHERE user_id = %s AND asset_type = %s ORDER BY created_at DESC", USE_SQLITE)
            cur.execute(query, (user_id, asset_type))
        else:
            query = adapt_query("SELECT * FROM assets WHERE user_id = %s ORDER BY created_at DESC", USE_SQLITE)
            cur.execute(query, (user_id,))
        rows = cur.fetchall()
        return [Asset(**_parse_row(dict_from_row(row, USE_SQLITE))) for row in rows]


@router.post("/assets", response_model=Asset, status_code=status.HTTP_201_CREATED)
async def create_asset(asset: AssetCreate, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        cur = get_cursor(conn)
        if USE_SQLITE:
            import uuid
            asset_id = str(uuid.uuid4())
            query = """INSERT INTO assets (id, user_id, name, description, asset_type, category,
                                           manufacturer, model_number, serial_number, purchase_date,
                                           purchase_price, condition, location, notes, context)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            cur.execute(query, (
                asset_id, asset.user_id, asset.name, asset.description, asset.asset_type,
                asset.category, asset.manufacturer, asset.model_number, asset.serial_number,
                asset.purchase_date, asset.purchase_price, asset.condition.value,
                asset.location, asset.notes, json.dumps(asset.context or {}),
            ))
            cur.execute("SELECT * FROM assets WHERE id = ?", (asset_id,))
        else:
            query = """INSERT INTO assets (id, user_id, name, description, asset_type, category,
                                           manufacturer, model_number, serial_number, purchase_date,
                                           purchase_price, condition, location, notes, context)
                       VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING *"""
            cur.execute(query, (
                asset.user_id, asset.name, asset.description, asset.asset_type,
                asset.category, asset.manufacturer, asset.model_number, asset.serial_number,
                asset.purchase_date, asset.purchase_price, asset.condition.value,
                asset.location, asset.notes, asset.context,
            ))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create asset")
        return Asset(**_parse_row(dict_from_row(row, USE_SQLITE)))


app.include_router(artemis_router.router, prefix=config.api_prefix)
app.include_router(router, prefix=config.api_prefix)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
