"""Education goals router — full CRUD via /education/api/v1/goals."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.database import get_db, get_cursor, USE_SQLITE
from core.logging_config import get_logger
from core import metrics
from models.goals import Goal, GoalCreate, GoalUpdate, VALID_CATEGORIES
from routers.auth import get_current_user
from core.auth_service import TokenData

log = get_logger('api.goals')
router = APIRouter(prefix='/education/api/v1/goals', tags=['goals'])


def _ph(n: int = 1) -> str:
    """Return correct placeholder for SQL — ? for SQLite, %s for Postgres."""
    return '?' if USE_SQLITE else '%s'


def _row_to_goal(row: dict) -> Goal:
    return Goal(
        id=row['id'],
        user_id=row['user_id'],
        title=row['title'],
        description=row.get('description') or '',
        category=row.get('category') or 'personal',
        target_date=row.get('target_date'),
        is_completed=bool(row['is_completed']),
        completed_at=row.get('completed_at'),
        created_at=str(row['created_at']),
        updated_at=str(row['updated_at']),
    )


@router.get('')
async def list_goals(
    status: Optional[str] = Query(None, description='Filter: active | completed'),
    sort: str = Query('createdAt', description='Sort field: createdAt | targetDate | title'),
    order: str = Query('desc', description='Sort order: asc | desc'),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """List all education goals for the authenticated user."""
    ph = _ph()
    query = f'SELECT * FROM education_goals WHERE user_id = {ph} AND deleted_at IS NULL'
    params: list = [current_user.user_id]

    if status == 'active':
        query += f' AND is_completed = 0'
    elif status == 'completed':
        query += f' AND is_completed = 1'

    sort_map = {'createdAt': 'created_at', 'targetDate': 'target_date', 'title': 'title'}
    db_sort = sort_map.get(sort, 'created_at')
    db_order = 'ASC' if order.lower() == 'asc' else 'DESC'
    query += f' ORDER BY {db_sort} {db_order}'

    count_query = query.replace('SELECT *', 'SELECT COUNT(*) as cnt').split(' ORDER BY')[0]

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(count_query, params)
        total_row = cur.fetchone()
        total = dict(total_row).get('cnt', 0) if total_row else 0

        query += f' LIMIT {ph} OFFSET {ph}'
        params.extend([limit, offset])
        cur.execute(query, params)
        rows = cur.fetchall()

    return {
        'data': [_row_to_goal(dict(r)).model_dump() for r in rows],
        'meta': {'total': total, 'limit': limit, 'offset': offset},
    }


@router.post('', status_code=status.HTTP_201_CREATED)
async def create_goal(
    goal: GoalCreate,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Create a new education goal."""
    if goal.category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'category must be one of: {", ".join(VALID_CATEGORIES)}',
        )
    ph = _ph()
    goal_id = str(uuid.uuid4())
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            f'INSERT INTO education_goals (id, user_id, title, description, category, target_date) '
            f'VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})',
            (goal_id, current_user.user_id, goal.title, goal.description, goal.category, goal.target_date),
        )
        conn.commit()
        cur.execute(f'SELECT * FROM education_goals WHERE id = {ph}', (goal_id,))
        row = cur.fetchone()

    log.info('goal_created', extra={'goal_id': goal_id, 'user_id': current_user.user_id})
    metrics.record_domain_event('goal_created')
    return {'data': _row_to_goal(dict(row)).model_dump()}


@router.get('/{goal_id}')
async def get_goal(
    goal_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Get a single education goal by ID, with activity counts."""
    ph = _ph()
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            f'SELECT * FROM education_goals WHERE id = {ph} AND user_id = {ph} AND deleted_at IS NULL',
            (goal_id, current_user.user_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Goal not found')

        # Count all activities across all plans linked to this goal
        cur.execute(
            f'SELECT COUNT(*) as total, SUM(is_completed) as done FROM activities WHERE goal_id = {ph}',
            (goal_id,),
        )
        counts = dict(cur.fetchone() or {})

    goal_dict = _row_to_goal(dict(row)).model_dump()
    goal_dict['activities_count'] = counts.get('total') or 0
    goal_dict['completed_activities_count'] = int(counts.get('done') or 0)
    return {'data': goal_dict}


@router.put('/{goal_id}')
async def update_goal(
    goal_id: str,
    updates: GoalUpdate,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Update an existing education goal."""
    ph = _ph()
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            f'SELECT id FROM education_goals WHERE id = {ph} AND user_id = {ph} AND deleted_at IS NULL',
            (goal_id, current_user.user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Goal not found')

        fields: dict = {k: v for k, v in updates.model_dump().items() if v is not None}
        if not fields:
            cur.execute(f'SELECT * FROM education_goals WHERE id = {ph}', (goal_id,))
            return {'data': _row_to_goal(dict(cur.fetchone())).model_dump()}

        if 'category' in fields and fields['category'] not in VALID_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'category must be one of: {", ".join(VALID_CATEGORIES)}',
            )

        now = datetime.now(timezone.utc).isoformat()
        db_fields: dict = {}
        for k, v in fields.items():
            db_key = 'is_completed' if k == 'is_completed' else k
            db_fields[db_key] = v
        db_fields['updated_at'] = now

        if fields.get('is_completed') is True:
            db_fields['completed_at'] = now
        elif fields.get('is_completed') is False:
            db_fields['completed_at'] = None

        set_clause = ', '.join(f'{k} = {ph}' for k in db_fields)
        cur.execute(
            f'UPDATE education_goals SET {set_clause} WHERE id = {ph} AND user_id = {ph}',
            [*db_fields.values(), goal_id, current_user.user_id],
        )
        conn.commit()
        cur.execute(f'SELECT * FROM education_goals WHERE id = {ph}', (goal_id,))
        row = cur.fetchone()

    log.info('goal_updated', extra={'goal_id': goal_id})
    metrics.record_domain_event('goal_updated')
    return {'data': _row_to_goal(dict(row)).model_dump()}


@router.delete('/{goal_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> None:
    """Soft-delete an education goal."""
    ph = _ph()
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            f'SELECT id FROM education_goals WHERE id = {ph} AND user_id = {ph} AND deleted_at IS NULL',
            (goal_id, current_user.user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Goal not found')
        cur.execute(
            f'UPDATE education_goals SET deleted_at = {ph}, updated_at = {ph} WHERE id = {ph}',
            (now, now, goal_id),
        )
        conn.commit()

    log.info('goal_deleted', extra={'goal_id': goal_id})
    metrics.record_domain_event('goal_deleted')
