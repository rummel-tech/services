"""Work-planner integration router for Vehicle Manager.

Contract: GET /work-planner/tasks
Surfaces upcoming and overdue maintenance records as WorkPlannerTask
objects for the work-planner Flutter app to display in the Home & Auto tab.
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from common.database import get_connection, get_cursor, dict_from_row, get_database_url, is_sqlite, adapt_query
from routers.auth import require_token, TokenData

USE_SQLITE = is_sqlite(get_database_url())
router = APIRouter(prefix="/work-planner", tags=["work-planner"])

# Surface maintenance records due within this many days (plus all overdue).
_LOOKAHEAD_DAYS = 30


class WorkPlannerTask(BaseModel):
    """Standardised task shape consumed by the work-planner app."""
    id: str
    title: str
    description: Optional[str] = None
    priority: str        # low | medium | high | urgent
    status: str          # open | in_progress | done
    due_date: Optional[str] = None   # YYYY-MM-DD
    category: str


def _priority_for_due_date(due: Optional[date]) -> str:
    if due is None:
        return "medium"
    today = date.today()
    if due < today:
        return "urgent"
    delta = (due - today).days
    if delta <= 7:
        return "high"
    if delta <= 14:
        return "medium"
    return "low"


@router.get("/tasks", response_model=List[WorkPlannerTask])
async def list_tasks_for_work_planner(token: TokenData = Depends(require_token)):
    """Return upcoming and overdue vehicle maintenance as work-planner tasks."""
    today = date.today()
    lookahead = today + timedelta(days=_LOOKAHEAD_DAYS)

    with get_connection() as conn:
        cur = get_cursor(conn)
        # Join maintenance_records with assets to include the vehicle name.
        query = adapt_query(
            """SELECT mr.id, mr.maintenance_type, mr.description, mr.next_due_date,
                      a.name AS vehicle_name
               FROM maintenance_records mr
               JOIN assets a ON a.id = mr.asset_id
               WHERE a.user_id = %s
                 AND mr.next_due_date IS NOT NULL
                 AND mr.next_due_date <= %s
               ORDER BY mr.next_due_date ASC""",
            USE_SQLITE,
        )
        cur.execute(query, (token.user_id, str(lookahead)))
        rows = cur.fetchall()

    tasks = []
    for row in rows:
        d = dict_from_row(row, USE_SQLITE)
        due_raw = d.get("next_due_date")
        due_date: Optional[date] = None
        if due_raw:
            try:
                due_date = date.fromisoformat(str(due_raw)[:10])
            except ValueError:
                pass

        maint_type = d.get("maintenance_type", "maintenance").replace("_", " ").title()
        vehicle = d.get("vehicle_name", "Vehicle")
        title = f"{maint_type} — {vehicle}"

        tasks.append(
            WorkPlannerTask(
                id=str(d["id"]),
                title=title,
                description=d.get("description"),
                priority=_priority_for_due_date(due_date),
                status="open",
                due_date=str(due_date) if due_date else None,
                category=d.get("maintenance_type", "maintenance"),
            )
        )
    return tasks
