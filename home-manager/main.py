"""
Home Manager API - Property and household management service.

Refactored to use common models and database persistence.
"""

import sys
from pathlib import Path
from typing import List, Optional
from uuid import UUID

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from common.models import (
    Task, Goal, Asset,
    TaskCreate, TaskUpdate,
    GoalCreate, GoalUpdate,
    AssetCreate, AssetUpdate,
    TaskStatus, Priority, AssetCondition
)
from common.database import (
    get_connection, get_cursor, dict_from_row,
    init_db, close_db, adapt_query, is_sqlite, get_database_url
)
from routers import artemis as artemis_router

# Initialize FastAPI app
app = FastAPI(
    title="Home Manager API",
    version="2.0.0",
    description="Property and household management service with database persistence"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(artemis_router.router)

# Check if using SQLite for query adaptation
USE_SQLITE = is_sqlite(get_database_url())


# Startup/shutdown events
@app.on_event("startup")
async def startup():
    """Initialize database connection pool."""
    init_db()


@app.on_event("shutdown")
async def shutdown():
    """Close database connection pool."""
    close_db()


# ============================================================================
# Health Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "home-manager"}


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    return {"status": "ready", "database": get_database_url()}


# ============================================================================
# Task Endpoints (using common Task model)
# ============================================================================

@app.get("/tasks/{user_id}", response_model=List[Task])
async def list_tasks(user_id: str):
    """List all tasks for a user."""
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query("SELECT * FROM tasks WHERE user_id = %s ORDER BY created_at DESC", USE_SQLITE)
        cur.execute(query, (user_id,))
        rows = cur.fetchall()
        return [Task(**dict_from_row(row, USE_SQLITE)) for row in rows]


@app.post("/tasks", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(task: TaskCreate):
    """Create a new task."""
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query(
            """INSERT INTO tasks (id, user_id, title, description, status, priority, category,
                                   due_date, estimated_minutes, tags, context)
               VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING *""",
            USE_SQLITE
        )

        if USE_SQLITE:
            import uuid
            task_id = str(uuid.uuid4())
            query = """INSERT INTO tasks (id, user_id, title, description, status, priority, category,
                                           due_date, estimated_minutes, tags, context)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            cur.execute(query, (
                task_id, task.user_id, task.title, task.description, task.status.value,
                task.priority.value, task.category, task.due_date, task.estimated_minutes,
                str(task.tags), str(task.context)
            ))
            cur.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        else:
            cur.execute(query, (
                task.user_id, task.title, task.description, task.status.value,
                task.priority.value, task.category, task.due_date, task.estimated_minutes,
                task.tags, task.context
            ))

        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create task")
        return Task(**dict_from_row(row, USE_SQLITE))


@app.get("/tasks/{user_id}/{task_id}", response_model=Task)
async def get_task(user_id: str, task_id: UUID):
    """Get a specific task."""
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query("SELECT * FROM tasks WHERE id = %s AND user_id = %s", USE_SQLITE)
        cur.execute(query, (str(task_id), user_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return Task(**dict_from_row(row, USE_SQLITE))


@app.put("/tasks/{user_id}/{task_id}", response_model=Task)
async def update_task(user_id: str, task_id: UUID, task_update: TaskUpdate):
    """Update a task."""
    updates = {k: v for k, v in task_update.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Build SET clause
    set_parts = []
    values = []
    for key, value in updates.items():
        set_parts.append(f"{key} = {'?' if USE_SQLITE else '%s'}")
        values.append(value.value if isinstance(value, (TaskStatus, Priority)) else value)

    values.extend([str(task_id), user_id])

    with get_connection() as conn:
        cur = get_cursor(conn)
        query = f"UPDATE tasks SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = {'?' if USE_SQLITE else '%s'} AND user_id = {'?' if USE_SQLITE else '%s'}"

        if USE_SQLITE:
            query = query.replace("NOW()", "CURRENT_TIMESTAMP")

        cur.execute(query, values)

        # Fetch updated row
        query = adapt_query("SELECT * FROM tasks WHERE id = %s AND user_id = %s", USE_SQLITE)
        cur.execute(query, (str(task_id), user_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return Task(**dict_from_row(row, USE_SQLITE))


@app.delete("/tasks/{user_id}/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(user_id: str, task_id: UUID):
    """Delete a task."""
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query("DELETE FROM tasks WHERE id = %s AND user_id = %s", USE_SQLITE)
        cur.execute(query, (str(task_id), user_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found")


# ============================================================================
# Goal Endpoints (using common Goal model)
# ============================================================================

@app.get("/goals/{user_id}", response_model=List[Goal])
async def list_goals(user_id: str):
    """List all goals for a user."""
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query("SELECT * FROM goals WHERE user_id = %s ORDER BY created_at DESC", USE_SQLITE)
        cur.execute(query, (user_id,))
        rows = cur.fetchall()
        return [Goal(**dict_from_row(row, USE_SQLITE)) for row in rows]


@app.post("/goals", response_model=Goal, status_code=status.HTTP_201_CREATED)
async def create_goal(goal: GoalCreate):
    """Create a new goal."""
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
                goal.target_value, goal.target_unit, goal.target_date, goal.notes, str(goal.context)
            ))
            cur.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
        else:
            query = """INSERT INTO goals (id, user_id, title, description, category, target_value,
                                          target_unit, target_date, notes, context)
                       VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING *"""
            cur.execute(query, (
                goal.user_id, goal.title, goal.description, goal.category,
                goal.target_value, goal.target_unit, goal.target_date, goal.notes, goal.context
            ))

        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create goal")
        return Goal(**dict_from_row(row, USE_SQLITE))


@app.get("/goals/{user_id}/{goal_id}", response_model=Goal)
async def get_goal(user_id: str, goal_id: UUID):
    """Get a specific goal."""
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query("SELECT * FROM goals WHERE id = %s AND user_id = %s", USE_SQLITE)
        cur.execute(query, (str(goal_id), user_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Goal not found")
        return Goal(**dict_from_row(row, USE_SQLITE))


# ============================================================================
# Asset Endpoints (using common Asset model)
# ============================================================================

@app.get("/assets/{user_id}", response_model=List[Asset])
async def list_assets(user_id: str, asset_type: Optional[str] = None):
    """List all assets for a user, optionally filtered by type."""
    with get_connection() as conn:
        cur = get_cursor(conn)
        if asset_type:
            query = adapt_query("SELECT * FROM assets WHERE user_id = %s AND asset_type = %s ORDER BY created_at DESC", USE_SQLITE)
            cur.execute(query, (user_id, asset_type))
        else:
            query = adapt_query("SELECT * FROM assets WHERE user_id = %s ORDER BY created_at DESC", USE_SQLITE)
            cur.execute(query, (user_id,))
        rows = cur.fetchall()
        return [Asset(**dict_from_row(row, USE_SQLITE)) for row in rows]


@app.post("/assets", response_model=Asset, status_code=status.HTTP_201_CREATED)
async def create_asset(asset: AssetCreate):
    """Create a new asset."""
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
                asset.location, asset.notes, str(asset.context)
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
                asset.location, asset.notes, asset.context
            ))

        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create asset")
        return Asset(**dict_from_row(row, USE_SQLITE))


# ============================================================================
# Legacy endpoint compatibility (for existing clients)
# ============================================================================

@app.get("/tasks/weekly/{user_id}")
async def get_weekly_tasks_legacy(user_id: str):
    """Legacy endpoint for weekly tasks."""
    tasks = await list_tasks(user_id)
    return {
        "user_id": user_id,
        "tasks": [task.dict() for task in tasks]
    }


@app.get("/goals/list/{user_id}")
async def get_goals_legacy(user_id: str):
    """Legacy endpoint for goals list."""
    goals = await list_goals(user_id)
    return [goal.dict() for goal in goals]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8020)
