"""Weekly plans router — /education/api/v1/plans."""

import uuid
from datetime import datetime, timezone, timedelta, date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.database import get_db, get_cursor, USE_SQLITE
from core.logging_config import get_logger
from core import metrics
from models.plans import Plan, PlanCreate, Activity, ActivityCreate, ActivityUpdate
from routers.auth import get_current_user
from core.auth_service import TokenData

log = get_logger('api.plans')
router = APIRouter(prefix='/education/api/v1/plans', tags=['plans'])


def _ph() -> str:
    return '?' if USE_SQLITE else '%s'


def _normalize_to_monday(date_str: str) -> str:
    """Normalize any ISO date to the Monday of that week."""
    try:
        d = date_type.fromisoformat(date_str[:10])
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Invalid date: {date_str}')
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


def _row_to_activity(row: dict) -> Activity:
    return Activity(
        id=row['id'],
        plan_id=row['plan_id'],
        goal_id=row.get('goal_id'),
        title=row['title'],
        description=row.get('description'),
        duration_minutes=row['duration_minutes'],
        actual_minutes=row.get('actual_minutes'),
        scheduled_time=str(row['scheduled_time']),
        is_completed=bool(row['is_completed']),
        completed_at=row.get('completed_at'),
        created_at=str(row['created_at']),
        updated_at=str(row['updated_at']),
    )


def _row_to_plan(row: dict, activities: list[Activity]) -> Plan:
    week_start = row['week_start_date']
    try:
        ws = date_type.fromisoformat(str(week_start)[:10])
        week_end = (ws + timedelta(days=6)).isoformat()
    except ValueError:
        week_end = week_start

    total_minutes = sum(a.duration_minutes for a in activities)
    completed = sum(1 for a in activities if a.is_completed)
    total = len(activities)
    pct = round((completed / total) * 100, 1) if total > 0 else 0.0

    return Plan(
        id=row['id'],
        user_id=row['user_id'],
        title=row['title'],
        week_start_date=str(week_start),
        week_end_date=week_end,
        activities=activities,
        total_planned_minutes=total_minutes,
        completion_percentage=pct,
        created_at=str(row['created_at']),
        updated_at=str(row['updated_at']),
    )


def _load_activities(conn, plan_id: str) -> list[Activity]:
    ph = _ph()
    cur = get_cursor(conn)
    cur.execute(
        f'SELECT * FROM activities WHERE plan_id = {ph} ORDER BY scheduled_time ASC',
        (plan_id,),
    )
    return [_row_to_activity(dict(r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Plans endpoints
# ---------------------------------------------------------------------------

@router.get('')
async def list_plans(
    week_start: Optional[str] = Query(None, description='ISO date for week start — defaults to current week'),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """List weekly plans for the authenticated user."""
    ph = _ph()
    query = f'SELECT * FROM weekly_plans WHERE user_id = {ph}'
    params: list = [current_user.user_id]

    if week_start:
        normalized = _normalize_to_monday(week_start)
        query += f' AND week_start_date = {ph}'
        params.append(normalized)

    count_q = query.replace('SELECT *', 'SELECT COUNT(*) as cnt')

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(count_q, params)
        total_row = cur.fetchone()
        total = dict(total_row).get('cnt', 0) if total_row else 0

        query += f' ORDER BY week_start_date DESC LIMIT {ph} OFFSET {ph}'
        params.extend([limit, offset])
        cur.execute(query, params)
        plan_rows = cur.fetchall()

        plans = []
        for r in plan_rows:
            row_dict = dict(r)
            activities = _load_activities(conn, row_dict['id'])
            plans.append(_row_to_plan(row_dict, activities).model_dump())

    return {'data': plans, 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.post('', status_code=status.HTTP_201_CREATED)
async def create_plan(
    plan: PlanCreate,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Create a new weekly plan. weekStartDate is normalized to Monday."""
    ph = _ph()
    monday = _normalize_to_monday(plan.week_start_date)
    plan_id = str(uuid.uuid4())

    with get_db() as conn:
        cur = get_cursor(conn)
        # Check for existing plan on that week
        cur.execute(
            f'SELECT id FROM weekly_plans WHERE user_id = {ph} AND week_start_date = {ph}',
            (current_user.user_id, monday),
        )
        existing = cur.fetchone()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'A plan for week starting {monday} already exists',
            )

        cur.execute(
            f'INSERT INTO weekly_plans (id, user_id, title, week_start_date) VALUES ({ph}, {ph}, {ph}, {ph})',
            (plan_id, current_user.user_id, plan.title, monday),
        )
        conn.commit()
        cur.execute(f'SELECT * FROM weekly_plans WHERE id = {ph}', (plan_id,))
        row = dict(cur.fetchone())

    log.info('plan_created', extra={'plan_id': plan_id, 'user_id': current_user.user_id})
    metrics.record_domain_event('plan_created')
    return {'data': _row_to_plan(row, []).model_dump()}


@router.get('/{plan_id}')
async def get_plan(
    plan_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Get a weekly plan with all its activities."""
    ph = _ph()
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            f'SELECT * FROM weekly_plans WHERE id = {ph} AND user_id = {ph}',
            (plan_id, current_user.user_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Plan not found')
        activities = _load_activities(conn, plan_id)

    return {'data': _row_to_plan(dict(row), activities).model_dump()}


# ---------------------------------------------------------------------------
# Activities sub-resource
# ---------------------------------------------------------------------------

@router.post('/{plan_id}/activities', status_code=status.HTTP_201_CREATED)
async def add_activity(
    plan_id: str,
    activity: ActivityCreate,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Add an activity to a weekly plan."""
    ph = _ph()
    with get_db() as conn:
        cur = get_cursor(conn)
        # Verify plan exists and belongs to user
        cur.execute(
            f'SELECT id FROM weekly_plans WHERE id = {ph} AND user_id = {ph}',
            (plan_id, current_user.user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Plan not found')

        # Verify goal exists if provided
        if activity.goal_id:
            cur.execute(
                f'SELECT id FROM education_goals WHERE id = {ph} AND user_id = {ph} AND deleted_at IS NULL',
                (activity.goal_id, current_user.user_id),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Goal not found')

        activity_id = str(uuid.uuid4())
        cur.execute(
            f'INSERT INTO activities (id, plan_id, goal_id, title, description, duration_minutes, scheduled_time) '
            f'VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})',
            (activity_id, plan_id, activity.goal_id, activity.title,
             activity.description, activity.duration_minutes, activity.scheduled_time),
        )
        # Update plan's updated_at
        now = datetime.now(timezone.utc).isoformat()
        cur.execute(
            f'UPDATE weekly_plans SET updated_at = {ph} WHERE id = {ph}',
            (now, plan_id),
        )
        conn.commit()
        cur.execute(f'SELECT * FROM activities WHERE id = {ph}', (activity_id,))
        row = cur.fetchone()

    log.info('activity_created', extra={'activity_id': activity_id, 'plan_id': plan_id})
    metrics.record_domain_event('activity_created')
    return {'data': _row_to_activity(dict(row)).model_dump()}


@router.patch('/{plan_id}/activities/{activity_id}')
async def update_activity(
    plan_id: str,
    activity_id: str,
    updates: ActivityUpdate,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Update an activity (including marking it complete)."""
    ph = _ph()
    with get_db() as conn:
        cur = get_cursor(conn)
        # Verify plan belongs to user
        cur.execute(
            f'SELECT id FROM weekly_plans WHERE id = {ph} AND user_id = {ph}',
            (plan_id, current_user.user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Plan not found')

        # Verify activity belongs to plan
        cur.execute(
            f'SELECT * FROM activities WHERE id = {ph} AND plan_id = {ph}',
            (activity_id, plan_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Activity not found')

        update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
        if not update_data:
            cur.execute(f'SELECT * FROM activities WHERE id = {ph}', (activity_id,))
            return {'data': _row_to_activity(dict(cur.fetchone())).model_dump()}

        now = datetime.now(timezone.utc).isoformat()
        db_fields = dict(update_data)
        db_fields['updated_at'] = now

        if update_data.get('is_completed') is True:
            db_fields['completed_at'] = now
        elif update_data.get('is_completed') is False:
            db_fields['completed_at'] = None

        set_clause = ', '.join(f'{k} = {ph}' for k in db_fields)
        cur.execute(
            f'UPDATE activities SET {set_clause} WHERE id = {ph} AND plan_id = {ph}',
            [*db_fields.values(), activity_id, plan_id],
        )
        # Update plan's updated_at
        cur.execute(f'UPDATE weekly_plans SET updated_at = {ph} WHERE id = {ph}', (now, plan_id))
        conn.commit()
        cur.execute(f'SELECT * FROM activities WHERE id = {ph}', (activity_id,))
        row = cur.fetchone()

    log.info('activity_updated', extra={'activity_id': activity_id})
    metrics.record_domain_event('activity_updated')
    return {'data': _row_to_activity(dict(row)).model_dump()}


@router.delete('/{plan_id}/activities/{activity_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_activity(
    plan_id: str,
    activity_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> None:
    """Delete an activity from a weekly plan."""
    ph = _ph()
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            f'SELECT id FROM weekly_plans WHERE id = {ph} AND user_id = {ph}',
            (plan_id, current_user.user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Plan not found')

        cur.execute(
            f'SELECT id FROM activities WHERE id = {ph} AND plan_id = {ph}',
            (activity_id, plan_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Activity not found')

        cur.execute(f'DELETE FROM activities WHERE id = {ph}', (activity_id,))
        now = datetime.now(timezone.utc).isoformat()
        cur.execute(f'UPDATE weekly_plans SET updated_at = {ph} WHERE id = {ph}', (now, plan_id))
        conn.commit()

    log.info('activity_deleted', extra={'activity_id': activity_id})
    metrics.record_domain_event('activity_deleted')
