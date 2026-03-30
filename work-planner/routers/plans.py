"""Plans router — CRUD for plans within a goal."""

import uuid
import json
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from core.database import get_db, get_cursor
from core.logging_config import get_logger
from core import metrics
from models.plans import Plan, PlanCreate, PlanUpdate
from routers.auth import get_current_user
from core.auth_service import TokenData

log = get_logger('api.plans')
router = APIRouter(prefix='/plans', tags=['plans'])


def _row_to_plan(row: dict) -> Plan:
    steps = row.get('steps', '[]')
    if isinstance(steps, str):
        steps = json.loads(steps)
    return Plan(
        id=row['id'],
        user_id=row['user_id'],
        goal_id=row['goal_id'],
        title=row['title'],
        description=row.get('description'),
        status=row['status'],
        start_date=row.get('start_date'),
        end_date=row.get('end_date'),
        steps=steps,
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


@router.get('', response_model=list[Plan])
async def list_plans(
    goal_id: Optional[str] = None,
    plan_status: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
) -> list[Plan]:
    """List plans for the current user, optionally filtered by goal or status."""
    with get_db() as conn:
        cur = get_cursor(conn)
        query = 'SELECT * FROM plans WHERE user_id = ?'
        params: list = [current_user.user_id]
        if goal_id:
            query += ' AND goal_id = ?'
            params.append(goal_id)
        if plan_status:
            query += ' AND status = ?'
            params.append(plan_status)
        query += ' ORDER BY created_at DESC'
        cur.execute(query, params)
        rows = cur.fetchall()
    return [_row_to_plan(dict(r)) for r in rows]


@router.post('', response_model=Plan, status_code=status.HTTP_201_CREATED)
async def create_plan(
    plan: PlanCreate,
    current_user: TokenData = Depends(get_current_user),
) -> Plan:
    """Create a new plan."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM goals WHERE id = ? AND user_id = ?', (plan.goal_id, current_user.user_id))
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Goal not found')

        plan_id = str(uuid.uuid4())
        cur.execute(
            """INSERT INTO plans (id, user_id, goal_id, title, description, status, start_date, end_date, steps)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (plan_id, current_user.user_id, plan.goal_id, plan.title, plan.description,
             plan.status, plan.start_date, plan.end_date, json.dumps(plan.steps)),
        )
        conn.commit()
        cur.execute('SELECT * FROM plans WHERE id = ?', (plan_id,))
        row = cur.fetchone()
    log.info('plan_created', extra={'plan_id': plan_id, 'goal_id': plan.goal_id})
    metrics.record_domain_event('plan_created')
    return _row_to_plan(dict(row))


@router.get('/{plan_id}', response_model=Plan)
async def get_plan(
    plan_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> Plan:
    """Get a single plan by ID."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT * FROM plans WHERE id = ? AND user_id = ?', (plan_id, current_user.user_id))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Plan not found')
    return _row_to_plan(dict(row))


@router.patch('/{plan_id}', response_model=Plan)
async def update_plan(
    plan_id: str,
    updates: PlanUpdate,
    current_user: TokenData = Depends(get_current_user),
) -> Plan:
    """Partially update a plan."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT * FROM plans WHERE id = ? AND user_id = ?', (plan_id, current_user.user_id))
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Plan not found')

        raw = updates.model_dump(exclude_none=True)
        if 'steps' in raw:
            raw['steps'] = json.dumps(raw['steps'])
        if raw:
            raw['updated_at'] = datetime.utcnow().isoformat()
            set_clause = ', '.join(f'{k} = ?' for k in raw)
            cur.execute(
                f'UPDATE plans SET {set_clause} WHERE id = ? AND user_id = ?',
                [*raw.values(), plan_id, current_user.user_id],
            )
            conn.commit()

        cur.execute('SELECT * FROM plans WHERE id = ?', (plan_id,))
        row = cur.fetchone()
    log.info('plan_updated', extra={'plan_id': plan_id})
    metrics.record_domain_event('plan_updated')
    return _row_to_plan(dict(row))


@router.delete('/{plan_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> None:
    """Delete a plan."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM plans WHERE id = ? AND user_id = ?', (plan_id, current_user.user_id))
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Plan not found')
        cur.execute('DELETE FROM plans WHERE id = ?', (plan_id,))
        conn.commit()
    log.info('plan_deleted', extra={'plan_id': plan_id})
    metrics.record_domain_event('plan_deleted')
