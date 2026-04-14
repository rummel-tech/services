"""Work-planner integration router for Home Manager.

Contract: GET /work-planner/tasks
Returns open and in-progress household tasks in the standardised
WorkPlannerTask format consumed by the work-planner Flutter app.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from common.database import get_connection, get_cursor, dict_from_row, get_database_url, is_sqlite, adapt_query
from routers.auth import require_token, TokenData

USE_SQLITE = is_sqlite(get_database_url())
router = APIRouter(prefix="/work-planner", tags=["work-planner"])


class WorkPlannerTask(BaseModel):
    """Standardised task shape consumed by the work-planner app."""
    id: str
    title: str
    description: Optional[str] = None
    priority: str        # low | medium | high | urgent
    status: str          # open | in_progress | done
    due_date: Optional[str] = None   # YYYY-MM-DD
    category: str


@router.get("/tasks", response_model=List[WorkPlannerTask])
async def list_tasks_for_work_planner(token: TokenData = Depends(require_token)):
    """Return all open and in-progress household tasks for the authenticated user."""
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query(
            """SELECT id, title, description, priority, status, due_date, category
               FROM tasks
               WHERE user_id = %s
                 AND status IN ('open', 'in_progress')
               ORDER BY
                 CASE priority
                   WHEN 'urgent' THEN 1
                   WHEN 'high'   THEN 2
                   WHEN 'medium' THEN 3
                   ELSE 4
                 END,
                 due_date ASC NULLS LAST""",
            USE_SQLITE,
        )
        cur.execute(query, (token.user_id,))
        rows = cur.fetchall()

    tasks = []
    for row in rows:
        d = dict_from_row(row, USE_SQLITE)
        # Normalise due_date to YYYY-MM-DD string
        due = d.get("due_date")
        if due and not isinstance(due, str):
            due = str(due)[:10]
        tasks.append(
            WorkPlannerTask(
                id=str(d["id"]),
                title=d["title"],
                description=d.get("description"),
                priority=d.get("priority", "medium"),
                status=d.get("status", "open"),
                due_date=due,
                category=d.get("category", "home"),
            )
        )
    return tasks
