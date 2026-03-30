"""Planners router — day planner, tasks, and week planner endpoints."""

import uuid
import json
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from core.database import get_db, get_cursor
from core.logging_config import get_logger
from core import metrics
from models.tasks import (
    DayPlanner, DayPlannerCreate, DayPlannerUpdate,
    Task, TaskCreate, TaskUpdate,
    WeekPlanner, WeekPlannerCreate, WeekPlannerUpdate,
)
from routers.auth import get_current_user
from core.auth_service import TokenData

log = get_logger('api.planners')
router = APIRouter(tags=['planners'])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_task(row: dict) -> Task:
    return Task(
        id=row['id'],
        user_id=row['user_id'],
        day_planner_id=row['day_planner_id'],
        title=row['title'],
        description=row.get('description'),
        priority=row['priority'],
        scheduled_time=row.get('scheduled_time'),
        duration_minutes=row.get('duration_minutes'),
        completed=bool(row['completed']),
        plan_id=row.get('plan_id'),
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


def _get_day_planner_with_tasks(conn, day_planner_id: str, user_id: str) -> Optional[DayPlanner]:
    cur = get_cursor(conn)
    cur.execute('SELECT * FROM day_planners WHERE id = ? AND user_id = ?', (day_planner_id, user_id))
    dp_row = cur.fetchone()
    if not dp_row:
        return None
    dp = dict(dp_row)
    cur.execute('SELECT * FROM tasks WHERE day_planner_id = ? ORDER BY scheduled_time ASC NULLS LAST', (day_planner_id,))
    tasks = [_row_to_task(dict(r)) for r in cur.fetchall()]
    return DayPlanner(
        id=dp['id'],
        user_id=dp['user_id'],
        date=dp['date'],
        notes=dp.get('notes'),
        tasks=tasks,
        created_at=dp['created_at'],
        updated_at=dp['updated_at'],
    )


# ---------------------------------------------------------------------------
# Day Planner
# ---------------------------------------------------------------------------

@router.get('/day-planners', response_model=list[DayPlanner])
async def list_day_planners(
    current_user: TokenData = Depends(get_current_user),
) -> list[DayPlanner]:
    """List all day planners for the current user."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM day_planners WHERE user_id = ? ORDER BY date DESC', (current_user.user_id,))
        ids = [r['id'] for r in cur.fetchall()]
        return [_get_day_planner_with_tasks(conn, dp_id, current_user.user_id) for dp_id in ids]


@router.post('/day-planners', response_model=DayPlanner, status_code=status.HTTP_201_CREATED)
async def create_day_planner(
    dp: DayPlannerCreate,
    current_user: TokenData = Depends(get_current_user),
) -> DayPlanner:
    """Create or retrieve the day planner for a given date (idempotent by date)."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM day_planners WHERE user_id = ? AND date = ?', (current_user.user_id, dp.date))
        existing = cur.fetchone()
        if existing:
            return _get_day_planner_with_tasks(conn, existing['id'], current_user.user_id)

        dp_id = str(uuid.uuid4())
        cur.execute(
            'INSERT INTO day_planners (id, user_id, date, notes) VALUES (?, ?, ?, ?)',
            (dp_id, current_user.user_id, dp.date, dp.notes),
        )
        conn.commit()
        return _get_day_planner_with_tasks(conn, dp_id, current_user.user_id)


@router.get('/day-planners/{date}', response_model=DayPlanner)
async def get_day_planner(
    date: str,
    current_user: TokenData = Depends(get_current_user),
) -> DayPlanner:
    """Get the day planner for a specific date (ISO format: YYYY-MM-DD)."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM day_planners WHERE user_id = ? AND date = ?', (current_user.user_id, date))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Day planner not found')
        return _get_day_planner_with_tasks(conn, row['id'], current_user.user_id)


@router.patch('/day-planners/{date}', response_model=DayPlanner)
async def update_day_planner(
    date: str,
    updates: DayPlannerUpdate,
    current_user: TokenData = Depends(get_current_user),
) -> DayPlanner:
    """Update notes on a day planner."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM day_planners WHERE user_id = ? AND date = ?', (current_user.user_id, date))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Day planner not found')
        dp_id = row['id']
        raw = updates.model_dump(exclude_none=True)
        if raw:
            raw['updated_at'] = datetime.utcnow().isoformat()
            set_clause = ', '.join(f'{k} = ?' for k in raw)
            cur.execute(f'UPDATE day_planners SET {set_clause} WHERE id = ?', [*raw.values(), dp_id])
            conn.commit()
        return _get_day_planner_with_tasks(conn, dp_id, current_user.user_id)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@router.post('/day-planners/{date}/tasks', response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(
    date: str,
    task: TaskCreate,
    current_user: TokenData = Depends(get_current_user),
) -> Task:
    """Add a task to the day planner for a given date (creates planner if needed)."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM day_planners WHERE user_id = ? AND date = ?', (current_user.user_id, date))
        row = cur.fetchone()
        if row:
            dp_id = row['id']
        else:
            dp_id = str(uuid.uuid4())
            cur.execute(
                'INSERT INTO day_planners (id, user_id, date) VALUES (?, ?, ?)',
                (dp_id, current_user.user_id, date),
            )

        task_id = str(uuid.uuid4())
        cur.execute(
            """INSERT INTO tasks (id, user_id, day_planner_id, title, description, priority,
               scheduled_time, duration_minutes, plan_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, current_user.user_id, dp_id, task.title, task.description,
             task.priority, task.scheduled_time, task.duration_minutes, task.plan_id),
        )
        conn.commit()
        cur.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
        task_row = cur.fetchone()
    log.info('task_created', extra={'task_id': task_id, 'date': date})
    metrics.record_domain_event('task_created')
    return _row_to_task(dict(task_row))


@router.patch('/tasks/{task_id}', response_model=Task)
async def update_task(
    task_id: str,
    updates: TaskUpdate,
    current_user: TokenData = Depends(get_current_user),
) -> Task:
    """Update a task (including toggling completion)."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT * FROM tasks WHERE id = ? AND user_id = ?', (task_id, current_user.user_id))
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')

        raw = updates.model_dump(exclude_none=True)
        if raw:
            raw['updated_at'] = datetime.utcnow().isoformat()
            set_clause = ', '.join(f'{k} = ?' for k in raw)
            cur.execute(
                f'UPDATE tasks SET {set_clause} WHERE id = ? AND user_id = ?',
                [*raw.values(), task_id, current_user.user_id],
            )
            conn.commit()

        cur.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
        row = cur.fetchone()
    log.info('task_updated', extra={'task_id': task_id})
    metrics.record_domain_event('task_updated')
    return _row_to_task(dict(row))


@router.delete('/tasks/{task_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> None:
    """Delete a task."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM tasks WHERE id = ? AND user_id = ?', (task_id, current_user.user_id))
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
        cur.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()
    log.info('task_deleted', extra={'task_id': task_id})
    metrics.record_domain_event('task_deleted')


# ---------------------------------------------------------------------------
# Week Planner
# ---------------------------------------------------------------------------

def _get_week_planner_full(conn, week_planner_id: str, user_id: str) -> Optional[WeekPlanner]:
    cur = get_cursor(conn)
    cur.execute('SELECT * FROM week_planners WHERE id = ? AND user_id = ?', (week_planner_id, user_id))
    wp_row = cur.fetchone()
    if not wp_row:
        return None
    wp = dict(wp_row)
    week_start = datetime.strptime(wp['week_start_date'], '%Y-%m-%d').date()
    day_planners = []
    for i in range(7):
        day = (week_start + timedelta(days=i)).isoformat()
        cur.execute('SELECT id FROM day_planners WHERE user_id = ? AND date = ?', (user_id, day))
        dp_row = cur.fetchone()
        if dp_row:
            dp = _get_day_planner_with_tasks(conn, dp_row['id'], user_id)
            if dp:
                day_planners.append(dp)

    goals = wp.get('weekly_goals', '[]')
    if isinstance(goals, str):
        goals = json.loads(goals)

    return WeekPlanner(
        id=wp['id'],
        user_id=wp['user_id'],
        week_start_date=wp['week_start_date'],
        weekly_goals=goals,
        notes=wp.get('notes'),
        day_planners=day_planners,
        created_at=wp['created_at'],
        updated_at=wp['updated_at'],
    )


@router.post('/week-planners', response_model=WeekPlanner, status_code=status.HTTP_201_CREATED)
async def create_week_planner(
    wp: WeekPlannerCreate,
    current_user: TokenData = Depends(get_current_user),
) -> WeekPlanner:
    """Create or retrieve the week planner for a given week start date."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            'SELECT id FROM week_planners WHERE user_id = ? AND week_start_date = ?',
            (current_user.user_id, wp.week_start_date),
        )
        existing = cur.fetchone()
        if existing:
            return _get_week_planner_full(conn, existing['id'], current_user.user_id)

        wp_id = str(uuid.uuid4())
        cur.execute(
            'INSERT INTO week_planners (id, user_id, week_start_date, weekly_goals, notes) VALUES (?, ?, ?, ?, ?)',
            (wp_id, current_user.user_id, wp.week_start_date, json.dumps(wp.weekly_goals), wp.notes),
        )
        conn.commit()
        return _get_week_planner_full(conn, wp_id, current_user.user_id)


@router.get('/week-planners/{week_start_date}', response_model=WeekPlanner)
async def get_week_planner(
    week_start_date: str,
    current_user: TokenData = Depends(get_current_user),
) -> WeekPlanner:
    """Get the week planner for a week starting on the given date."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            'SELECT id FROM week_planners WHERE user_id = ? AND week_start_date = ?',
            (current_user.user_id, week_start_date),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Week planner not found')
        return _get_week_planner_full(conn, row['id'], current_user.user_id)


@router.patch('/week-planners/{week_start_date}', response_model=WeekPlanner)
async def update_week_planner(
    week_start_date: str,
    updates: WeekPlannerUpdate,
    current_user: TokenData = Depends(get_current_user),
) -> WeekPlanner:
    """Update weekly goals or notes for a week planner."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            'SELECT id FROM week_planners WHERE user_id = ? AND week_start_date = ?',
            (current_user.user_id, week_start_date),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Week planner not found')
        wp_id = row['id']

        raw = updates.model_dump(exclude_none=True)
        if 'weekly_goals' in raw:
            raw['weekly_goals'] = json.dumps(raw['weekly_goals'])
        if raw:
            raw['updated_at'] = datetime.utcnow().isoformat()
            set_clause = ', '.join(f'{k} = ?' for k in raw)
            cur.execute(f'UPDATE week_planners SET {set_clause} WHERE id = ?', [*raw.values(), wp_id])
            conn.commit()
        return _get_week_planner_full(conn, wp_id, current_user.user_id)


@router.get('/week-planners/{week_start_date}/stats')
async def get_week_stats(
    week_start_date: str,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Return completion statistics for a given week."""
    week_start = datetime.strptime(week_start_date, '%Y-%m-%d').date()
    dates = [(week_start + timedelta(days=i)).isoformat() for i in range(7)]
    with get_db() as conn:
        cur = get_cursor(conn)
        placeholders = ','.join('?' * 7)
        cur.execute(
            f"""SELECT t.completed FROM tasks t
                JOIN day_planners dp ON t.day_planner_id = dp.id
                WHERE dp.user_id = ? AND dp.date IN ({placeholders})""",
            [current_user.user_id, *dates],
        )
        rows = cur.fetchall()

    total = len(rows)
    completed = sum(1 for r in rows if r['completed'])
    return {
        'week_start_date': week_start_date,
        'total_tasks': total,
        'completed_tasks': completed,
        'completion_rate': round(completed / total, 2) if total > 0 else 0.0,
    }
