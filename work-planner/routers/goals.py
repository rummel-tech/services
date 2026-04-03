"""Goals router — CRUD for user goals."""

import uuid
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from core.database import get_db, get_cursor
from core.logging_config import get_logger
from core import metrics
from models.goals import Goal, GoalCreate, GoalUpdate
from routers.auth import get_current_user
from core.auth_service import TokenData

log = get_logger('api.goals')
router = APIRouter(prefix='/goals', tags=['goals'])


def _row_to_goal(row: dict) -> Goal:
    return Goal(
        id=row['id'],
        user_id=row['user_id'],
        title=row['title'],
        description=row.get('description'),
        goal_type=row['goal_type'],
        status=row['status'],
        target_date=row.get('target_date'),
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


@router.get('', response_model=list[Goal])
async def list_goals(
    goal_type: Optional[str] = None,
    goal_status: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
) -> list[Goal]:
    """List all goals for the current user, with optional type/status filters."""
    with get_db() as conn:
        cur = get_cursor(conn)
        query = 'SELECT * FROM goals WHERE user_id = ?'
        params: list = [current_user.user_id]
        if goal_type:
            query += ' AND goal_type = ?'
            params.append(goal_type)
        if goal_status:
            query += ' AND status = ?'
            params.append(goal_status)
        query += ' ORDER BY created_at DESC'
        cur.execute(query, params)
        rows = cur.fetchall()
    return [_row_to_goal(dict(r)) for r in rows]


@router.post('', response_model=Goal, status_code=status.HTTP_201_CREATED)
async def create_goal(
    goal: GoalCreate,
    current_user: TokenData = Depends(get_current_user),
) -> Goal:
    """Create a new goal."""
    goal_id = str(uuid.uuid4())
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """INSERT INTO goals (id, user_id, title, description, goal_type, status, target_date)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (goal_id, current_user.user_id, goal.title, goal.description,
             goal.goal_type, goal.status, goal.target_date),
        )
        conn.commit()
        cur.execute('SELECT * FROM goals WHERE id = ?', (goal_id,))
        row = cur.fetchone()
    log.info('goal_created', extra={'goal_id': goal_id, 'user_id': current_user.user_id})
    metrics.record_domain_event('goal_created')
    return _row_to_goal(dict(row))


@router.get('/{goal_id}', response_model=Goal)
async def get_goal(
    goal_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> Goal:
    """Get a single goal by ID."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT * FROM goals WHERE id = ? AND user_id = ?', (goal_id, current_user.user_id))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Goal not found')
    return _row_to_goal(dict(row))


@router.patch('/{goal_id}', response_model=Goal)
async def update_goal(
    goal_id: str,
    updates: GoalUpdate,
    current_user: TokenData = Depends(get_current_user),
) -> Goal:
    """Partially update a goal."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT * FROM goals WHERE id = ? AND user_id = ?', (goal_id, current_user.user_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Goal not found')

        fields = {k: v for k, v in updates.model_dump().items() if v is not None}
        if fields:
            fields['updated_at'] = datetime.now(timezone.utc).isoformat()
            set_clause = ', '.join(f'{k} = ?' for k in fields)
            cur.execute(
                f'UPDATE goals SET {set_clause} WHERE id = ? AND user_id = ?',
                [*fields.values(), goal_id, current_user.user_id],
            )
            conn.commit()

        cur.execute('SELECT * FROM goals WHERE id = ?', (goal_id,))
        row = cur.fetchone()
    log.info('goal_updated', extra={'goal_id': goal_id})
    metrics.record_domain_event('goal_updated')
    return _row_to_goal(dict(row))


@router.delete('/{goal_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> None:
    """Delete a goal and all its associated plans."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM goals WHERE id = ? AND user_id = ?', (goal_id, current_user.user_id))
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Goal not found')
        cur.execute('DELETE FROM plans WHERE goal_id = ?', (goal_id,))
        cur.execute('DELETE FROM goals WHERE id = ?', (goal_id,))
        conn.commit()
    log.info('goal_deleted', extra={'goal_id': goal_id})
    metrics.record_domain_event('goal_deleted')
