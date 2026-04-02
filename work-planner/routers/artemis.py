"""Artemis Module Contract endpoints for Work Planner.

Accepts both standalone work-planner tokens AND Artemis platform tokens
(iss == "artemis-auth") via the shared dual-token auth in common/.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from common.artemis_auth import create_artemis_token_dependency
from core.auth_service import TokenData, decode_token
from core.database import get_db, get_cursor

router = APIRouter(prefix='/artemis', tags=['artemis'])

require_token = create_artemis_token_dependency(
    standalone_decoder=decode_token,
    token_data_class=TokenData,
)


# ---------------------------------------------------------------------------
# Module manifest (static — no auth required per contract)
# ---------------------------------------------------------------------------

MODULE_MANIFEST = {
    'module': {
        'id': 'work-planner',
        'name': 'Work Planner',
        'version': '0.1.0',
        'description': 'Task management, project tracking, and work session planning',
        'icon': 'work',
        'color': '#3b82f6',
        'contract_version': '1.0',
    },
    'capabilities': {
        'auth': {
            'accepts_artemis_token': True,
            'standalone_auth': True,
        },
        'dashboard_widgets': [
            {
                'id': 'todays_tasks',
                'name': "Today's Tasks",
                'description': "Shows today's task list and completion rate",
                'size': 'medium',
                'data_endpoint': '/artemis/widgets/todays_tasks',
                'refresh_seconds': 300,
            },
            {
                'id': 'weekly_progress',
                'name': 'Weekly Progress',
                'description': 'Task completion rate for the current week',
                'size': 'small',
                'data_endpoint': '/artemis/widgets/weekly_progress',
                'refresh_seconds': 3600,
            },
        ],
        'quick_actions': [
            {
                'id': 'add_task',
                'label': 'Add Task',
                'icon': 'add_task',
                'endpoint': '/artemis/actions/add_task',
                'method': 'POST',
            },
        ],
        'agent_tools': [
            {
                'id': 'get_todays_tasks',
                'description': "Get the user's tasks for today or a specific date",
                'endpoint': '/artemis/agent/get_todays_tasks',
                'method': 'GET',
                'parameters': {
                    'date': {'type': 'string', 'description': 'ISO date, defaults to today', 'required': False},
                },
            },
            {
                'id': 'create_task',
                'description': 'Create a new task for a specific date',
                'endpoint': '/artemis/agent/create_task',
                'method': 'POST',
                'parameters': {
                    'title': {'type': 'string', 'required': True},
                    'date': {'type': 'string', 'description': 'ISO date, defaults to today', 'required': False},
                    'priority': {'type': 'string', 'description': 'low | medium | high | urgent', 'required': False},
                },
            },
            {
                'id': 'get_weekly_summary',
                'description': 'Get task completion summary for the current or specified week',
                'endpoint': '/artemis/agent/get_weekly_summary',
                'method': 'GET',
                'parameters': {
                    'week_start': {'type': 'string', 'description': 'ISO date of Monday', 'required': False},
                },
            },
        ],
        'provides_data': [
            {
                'id': 'task_schedule',
                'name': 'Task Schedule',
                'description': 'Upcoming scheduled tasks',
                'endpoint': '/artemis/data/task_schedule',
                'requires_permission': 'work.tasks.read',
            },
            {
                'id': 'goals_progress',
                'name': 'Goals Progress',
                'description': 'Active goal completion rates',
                'endpoint': '/artemis/data/goals_progress',
                'requires_permission': 'work.goals.read',
            },
        ],
        'consumes_data': [],
    },
}


@router.get('/manifest')
async def get_manifest() -> dict:
    """Return the Artemis module capability manifest."""
    return MODULE_MANIFEST


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create_day_planner(conn, user_id: str, date_str: str) -> str:
    """Return the day_planner id for the given date, creating it if needed."""
    cur = get_cursor(conn)
    cur.execute('SELECT id FROM day_planners WHERE user_id = ? AND date = ?', (user_id, date_str))
    row = cur.fetchone()
    if row:
        return row['id']
    dp_id = str(uuid.uuid4())
    cur.execute(
        'INSERT INTO day_planners (id, user_id, date) VALUES (?, ?, ?)',
        (dp_id, user_id, date_str),
    )
    conn.commit()
    return dp_id


def _task_summary(row: dict) -> dict:
    return {
        'id': row['id'],
        'title': row['title'],
        'priority': row['priority'],
        'scheduled_time': row.get('scheduled_time'),
        'duration_minutes': row.get('duration_minutes'),
        'completed': bool(row['completed']),
    }


# ---------------------------------------------------------------------------
# Widget endpoints
# ---------------------------------------------------------------------------

@router.get('/widgets/todays_tasks')
async def widget_todays_tasks(token: TokenData = Depends(require_token)) -> dict:
    """Today's task list and completion rate."""
    today = datetime.today().date().isoformat()
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM day_planners WHERE user_id = ? AND date = ?', (token.user_id, today))
        dp_row = cur.fetchone()
        if not dp_row:
            return {'widget_id': 'todays_tasks', 'date': today, 'tasks': [], 'total': 0, 'completed': 0, 'completion_rate': 0.0}
        cur.execute(
            'SELECT * FROM tasks WHERE day_planner_id = ? ORDER BY scheduled_time ASC NULLS LAST',
            (dp_row['id'],),
        )
        rows = [dict(r) for r in cur.fetchall()]

    total = len(rows)
    completed = sum(1 for t in rows if t['completed'])
    return {
        'widget_id': 'todays_tasks',
        'date': today,
        'tasks': [_task_summary(t) for t in rows],
        'total': total,
        'completed': completed,
        'completion_rate': round(completed / total, 2) if total > 0 else 0.0,
    }


@router.get('/widgets/weekly_progress')
async def widget_weekly_progress(token: TokenData = Depends(require_token)) -> dict:
    """Task completion rate for the current week."""
    today = datetime.today().date()
    monday = today - timedelta(days=today.weekday())
    dates = [(monday + timedelta(days=i)).isoformat() for i in range(7)]

    with get_db() as conn:
        cur = get_cursor(conn)
        placeholders = ','.join('?' * 7)
        cur.execute(
            f"""SELECT t.completed FROM tasks t
                JOIN day_planners dp ON t.day_planner_id = dp.id
                WHERE dp.user_id = ? AND dp.date IN ({placeholders})""",
            [token.user_id, *dates],
        )
        rows = cur.fetchall()

    total = len(rows)
    completed = sum(1 for r in rows if r['completed'])
    return {
        'widget_id': 'weekly_progress',
        'week_start': monday.isoformat(),
        'total': total,
        'completed': completed,
        'completion_rate': round(completed / total, 2) if total > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# Agent tool endpoints
# ---------------------------------------------------------------------------

@router.get('/agent/get_todays_tasks')
async def agent_get_todays_tasks(
    date: Optional[str] = Query(None, description='ISO date, defaults to today'),
    token: TokenData = Depends(require_token),
) -> dict:
    """Get the user's tasks for today or a specific date."""
    target = date or datetime.today().date().isoformat()
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM day_planners WHERE user_id = ? AND date = ?', (token.user_id, target))
        dp_row = cur.fetchone()
        if not dp_row:
            return {'date': target, 'tasks': [], 'total': 0, 'completed': 0}
        cur.execute(
            'SELECT * FROM tasks WHERE day_planner_id = ? ORDER BY scheduled_time ASC NULLS LAST',
            (dp_row['id'],),
        )
        rows = [dict(r) for r in cur.fetchall()]

    total = len(rows)
    completed = sum(1 for t in rows if t['completed'])
    return {
        'date': target,
        'tasks': [_task_summary(t) for t in rows],
        'total': total,
        'completed': completed,
    }


class AgentCreateTaskBody(BaseModel):
    title: str
    date: Optional[str] = None       # ISO date, defaults to today
    priority: str = 'medium'         # low | medium | high | urgent
    description: Optional[str] = None
    scheduled_time: Optional[str] = None
    duration_minutes: Optional[int] = None


@router.post('/agent/create_task')
async def agent_create_task(
    body: AgentCreateTaskBody,
    token: TokenData = Depends(require_token),
) -> dict:
    """Create a new task for a specific date."""
    target = body.date or datetime.today().date().isoformat()
    task_id = str(uuid.uuid4())

    with get_db() as conn:
        dp_id = _get_or_create_day_planner(conn, token.user_id, target)
        cur = get_cursor(conn)
        cur.execute(
            """INSERT INTO tasks (id, user_id, day_planner_id, title, description,
               priority, scheduled_time, duration_minutes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, token.user_id, dp_id, body.title, body.description,
             body.priority, body.scheduled_time, body.duration_minutes),
        )
        conn.commit()
        cur.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
        row = dict(cur.fetchone())

    return {'success': True, 'task': _task_summary(row), 'date': target}


@router.get('/agent/get_weekly_summary')
async def agent_get_weekly_summary(
    week_start: Optional[str] = Query(None, description='ISO date of Monday, defaults to current week'),
    token: TokenData = Depends(require_token),
) -> dict:
    """Get task completion summary for the current or specified week."""
    if week_start:
        monday = datetime.strptime(week_start, '%Y-%m-%d').date()
    else:
        today = datetime.today().date()
        monday = today - timedelta(days=today.weekday())

    dates = [(monday + timedelta(days=i)).isoformat() for i in range(7)]

    with get_db() as conn:
        cur = get_cursor(conn)
        placeholders = ','.join('?' * 7)
        cur.execute(
            f"""SELECT t.id, t.title, t.priority, t.completed, dp.date
                FROM tasks t
                JOIN day_planners dp ON t.day_planner_id = dp.id
                WHERE dp.user_id = ? AND dp.date IN ({placeholders})
                ORDER BY dp.date ASC, t.scheduled_time ASC NULLS LAST""",
            [token.user_id, *dates],
        )
        rows = [dict(r) for r in cur.fetchall()]

    total = len(rows)
    completed = sum(1 for r in rows if r['completed'])

    by_day = {}
    for r in rows:
        d = r['date']
        if d not in by_day:
            by_day[d] = {'total': 0, 'completed': 0}
        by_day[d]['total'] += 1
        if r['completed']:
            by_day[d]['completed'] += 1

    return {
        'week_start': monday.isoformat(),
        'total': total,
        'completed': completed,
        'completion_rate': round(completed / total, 2) if total > 0 else 0.0,
        'by_day': by_day,
    }


# ---------------------------------------------------------------------------
# Quick action endpoints
# ---------------------------------------------------------------------------

@router.post('/actions/add_task')
async def action_add_task(
    body: AgentCreateTaskBody,
    token: TokenData = Depends(require_token),
) -> dict:
    """Quick action: add a task to today's planner."""
    return await agent_create_task(body, token)


# ---------------------------------------------------------------------------
# Cross-module data endpoints
# ---------------------------------------------------------------------------

@router.get('/data/task_schedule')
async def data_task_schedule(
    days: int = Query(7, description='Number of days ahead to include'),
    token: TokenData = Depends(require_token),
) -> dict:
    """Upcoming scheduled tasks for the next N days."""
    today = datetime.today().date()
    dates = [(today + timedelta(days=i)).isoformat() for i in range(days)]

    with get_db() as conn:
        cur = get_cursor(conn)
        placeholders = ','.join('?' * len(dates))
        cur.execute(
            f"""SELECT t.id, t.title, t.priority, t.scheduled_time, t.duration_minutes,
                       t.completed, dp.date
                FROM tasks t
                JOIN day_planners dp ON t.day_planner_id = dp.id
                WHERE dp.user_id = ? AND dp.date IN ({placeholders}) AND t.completed = 0
                ORDER BY dp.date ASC, t.scheduled_time ASC NULLS LAST""",
            [token.user_id, *dates],
        )
        rows = [dict(r) for r in cur.fetchall()]

    return {
        'from': today.isoformat(),
        'days': days,
        'tasks': [
            {
                'id': r['id'],
                'title': r['title'],
                'priority': r['priority'],
                'date': r['date'],
                'scheduled_time': r.get('scheduled_time'),
                'duration_minutes': r.get('duration_minutes'),
            }
            for r in rows
        ],
    }


@router.get('/data/goals_progress')
async def data_goals_progress(token: TokenData = Depends(require_token)) -> dict:
    """Active goals with completion status."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """SELECT * FROM goals WHERE user_id = ? AND status != 'completed'
               ORDER BY target_date ASC NULLS LAST, created_at DESC""",
            (token.user_id,),
        )
        goals = [dict(r) for r in cur.fetchall()]

    return {
        'goals': [
            {
                'id': g['id'],
                'title': g['title'],
                'goal_type': g['goal_type'],
                'status': g['status'],
                'target_date': g.get('target_date'),
            }
            for g in goals
        ],
        'total': len(goals),
    }
