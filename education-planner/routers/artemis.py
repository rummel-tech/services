"""Artemis Module Contract endpoints for Education Planner.

Accepts both standalone education-planner tokens AND Artemis platform tokens
(iss == "artemis-auth") via the shared dual-token auth in common/.
"""

import uuid
from datetime import datetime, timezone, timedelta, date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from common.artemis_auth import create_artemis_token_dependency
from core.auth_service import TokenData, decode_token
from core.database import get_db, get_cursor, USE_SQLITE

router = APIRouter(prefix='/artemis', tags=['artemis'])

require_token = create_artemis_token_dependency(
    standalone_decoder=decode_token,
    token_data_class=TokenData,
)


# ---------------------------------------------------------------------------
# Module manifest
# ---------------------------------------------------------------------------

VERSION = '1.0.0'

MANIFEST = {
    'module': {
        'id': 'education-planner',
        'name': 'Education Planner',
        'version': VERSION,
        'contract_version': '1.0',
        'description': 'Goal-oriented learning management with weekly activity planning',
        'icon': 'school',
        'color': '#1E88E5',
        'standalone_url': 'https://rummel-tech.github.io/education-planner/',
        'api_base': 'https://api.rummeltech.com/education-planner',
    },
    'capabilities': {
        'auth': {
            'accepts_artemis_token': True,
            'standalone_auth': True,
        },
        'dashboard_widgets': [
            {
                'id': 'active_goals',
                'name': 'Active Goals',
                'description': 'Count and summary of active education goals',
                'size': 'small',
                'data_endpoint': '/artemis/widgets/active_goals',
                'refresh_seconds': 3600,
            },
            {
                'id': 'this_weeks_plan',
                'name': "This Week's Study Plan",
                'description': 'Activities scheduled for the current week and completion rate',
                'size': 'medium',
                'data_endpoint': '/artemis/widgets/this_weeks_plan',
                'refresh_seconds': 300,
            },
        ],
        'quick_actions': [
            {
                'id': 'create_goal',
                'label': 'New Learning Goal',
                'icon': 'add_circle',
                'endpoint': '/artemis/agent/create_goal',
                'method': 'POST',
            },
            {
                'id': 'add_activity',
                'label': 'Schedule Study Session',
                'icon': 'event',
                'endpoint': '/artemis/agent/add_activity',
                'method': 'POST',
            },
        ],
        'agent_tools': [
            {
                'id': 'get_goals',
                'description': "Get the user's education goals, optionally filtered by status",
                'endpoint': '/artemis/agent/get_goals',
                'method': 'GET',
                'parameters': {
                    'status': {
                        'type': 'string',
                        'description': 'Filter: active | completed | all (default: all)',
                        'required': False,
                    },
                },
            },
            {
                'id': 'create_goal',
                'description': 'Create a new education goal for the user',
                'endpoint': '/artemis/agent/create_goal',
                'method': 'POST',
                'parameters': {
                    'title': {'type': 'string', 'description': 'Goal title', 'required': True},
                    'description': {'type': 'string', 'description': 'Goal description', 'required': False},
                    'category': {
                        'type': 'string',
                        'description': 'professional | personal | hobby | academic',
                        'required': False,
                    },
                    'target_date': {
                        'type': 'string',
                        'description': 'ISO date for target completion',
                        'required': False,
                    },
                },
            },
            {
                'id': 'get_weekly_plan',
                'description': "Get the user's weekly study plan with all activities",
                'endpoint': '/artemis/agent/get_weekly_plan',
                'method': 'GET',
                'parameters': {
                    'week_start': {
                        'type': 'string',
                        'description': 'ISO date of any day in the week (defaults to current week)',
                        'required': False,
                    },
                },
            },
            {
                'id': 'add_activity',
                'description': 'Schedule a study activity in the current or specified weekly plan',
                'endpoint': '/artemis/agent/add_activity',
                'method': 'POST',
                'parameters': {
                    'title': {'type': 'string', 'description': 'Activity title', 'required': True},
                    'scheduled_time': {
                        'type': 'string',
                        'description': 'ISO datetime for when the activity is scheduled',
                        'required': True,
                    },
                    'duration_minutes': {'type': 'number', 'description': 'Duration in minutes', 'required': True},
                    'goal_id': {'type': 'string', 'description': 'ID of associated goal (optional)', 'required': False},
                    'description': {'type': 'string', 'required': False},
                },
            },
            {
                'id': 'complete_activity',
                'description': 'Mark a study activity as completed',
                'endpoint': '/artemis/agent/complete_activity',
                'method': 'POST',
                'parameters': {
                    'activity_id': {'type': 'string', 'description': 'Activity ID to mark complete', 'required': True},
                    'actual_minutes': {
                        'type': 'number',
                        'description': 'Actual time spent in minutes (optional)',
                        'required': False,
                    },
                },
            },
            {
                'id': 'get_weekly_summary',
                'description': 'Get a completion summary for the current or specified week',
                'endpoint': '/artemis/agent/get_weekly_summary',
                'method': 'GET',
                'parameters': {
                    'week_start': {
                        'type': 'string',
                        'description': 'ISO date of any day in the week (defaults to current week)',
                        'required': False,
                    },
                },
            },
        ],
        'provides_data': [
            {
                'id': 'study_schedule',
                'name': 'Study Schedule',
                'description': 'Upcoming study activities for the next 14 days',
                'endpoint': '/artemis/data/study_schedule',
                'schema': {
                    'activities': 'array',
                    'date_range': 'object',
                },
                'requires_permission': 'education.schedule.read',
            },
            {
                'id': 'goals_progress',
                'name': 'Goals Progress',
                'description': 'Active education goals with completion rates',
                'endpoint': '/artemis/data/goals_progress',
                'schema': {
                    'goals': 'array',
                    'total_active': 'number',
                    'total_completed': 'number',
                },
                'requires_permission': 'education.goals.read',
            },
        ],
        'consumes_data': [],
        'optional_endpoints': [
            {
                'path': '/artemis/summary',
                'description': 'Natural language education progress summary for AI briefings',
            },
            {
                'path': '/artemis/calendar',
                'description': 'Upcoming study activities as calendar events',
            },
        ],
    },
}


@router.get('/manifest')
def get_manifest() -> dict:
    """Return the Artemis module capability manifest. No auth required."""
    return MANIFEST


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _ph() -> str:
    return '?' if USE_SQLITE else '%s'


def _get_current_week_monday() -> str:
    today = date_type.today()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def _normalize_to_monday(date_str: str) -> str:
    try:
        d = date_type.fromisoformat(date_str[:10])
    except ValueError:
        return _get_current_week_monday()
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


def _get_or_create_plan_for_week(conn, user_id: str, monday: str) -> dict:
    """Get existing plan for given week or create one."""
    ph = _ph()
    cur = get_cursor(conn)
    cur.execute(
        f'SELECT * FROM weekly_plans WHERE user_id = {ph} AND week_start_date = {ph}',
        (user_id, monday),
    )
    row = cur.fetchone()
    if row:
        return dict(row)

    plan_id = str(uuid.uuid4())
    ws = date_type.fromisoformat(monday)
    we = ws + timedelta(days=6)
    title = f'Week of {ws.strftime("%b %-d")}'
    cur.execute(
        f'INSERT INTO weekly_plans (id, user_id, title, week_start_date) VALUES ({ph}, {ph}, {ph}, {ph})',
        (plan_id, user_id, title, monday),
    )
    conn.commit()
    cur.execute(f'SELECT * FROM weekly_plans WHERE id = {ph}', (plan_id,))
    return dict(cur.fetchone())


# ---------------------------------------------------------------------------
# Dashboard widgets
# ---------------------------------------------------------------------------

@router.get('/widgets/{widget_id}')
def get_widget(
    widget_id: str,
    token: TokenData = Depends(require_token),
) -> dict:
    """Return live widget data."""
    user_id = token.user_id
    ph = _ph()
    now = datetime.now(timezone.utc).isoformat()

    if widget_id == 'active_goals':
        with get_db() as conn:
            cur = get_cursor(conn)
            cur.execute(
                f'SELECT COUNT(*) as total FROM education_goals WHERE user_id = {ph} AND is_completed = 0 AND deleted_at IS NULL',
                (user_id,),
            )
            total = dict(cur.fetchone()).get('total', 0)
            cur.execute(
                f'SELECT COUNT(*) as done FROM education_goals WHERE user_id = {ph} AND is_completed = 1 AND deleted_at IS NULL',
                (user_id,),
            )
            done = dict(cur.fetchone()).get('done', 0)
            cur.execute(
                f'SELECT title, target_date FROM education_goals '
                f'WHERE user_id = {ph} AND is_completed = 0 AND deleted_at IS NULL '
                f'ORDER BY target_date ASC LIMIT 3',
                (user_id,),
            )
            upcoming = [dict(r) for r in cur.fetchall()]

        return {
            'widget_id': 'active_goals',
            'data': {
                'active_count': total,
                'completed_count': done,
                'upcoming_deadlines': upcoming,
            },
            'last_updated': now,
        }

    elif widget_id == 'this_weeks_plan':
        monday = _get_current_week_monday()
        ws = date_type.fromisoformat(monday)
        sunday = (ws + timedelta(days=6)).isoformat()

        with get_db() as conn:
            cur = get_cursor(conn)
            cur.execute(
                f'SELECT id, title FROM weekly_plans WHERE user_id = {ph} AND week_start_date = {ph}',
                (user_id, monday),
            )
            plan_row = cur.fetchone()
            if not plan_row:
                return {
                    'widget_id': 'this_weeks_plan',
                    'data': {
                        'has_plan': False,
                        'week_start': monday,
                        'week_end': sunday,
                    },
                    'last_updated': now,
                }
            plan = dict(plan_row)
            cur.execute(
                f'SELECT COUNT(*) as total, SUM(is_completed) as done, SUM(duration_minutes) as mins '
                f'FROM activities WHERE plan_id = {ph}',
                (plan['id'],),
            )
            stats = dict(cur.fetchone() or {})

        total_acts = stats.get('total') or 0
        done_acts = int(stats.get('done') or 0)
        return {
            'widget_id': 'this_weeks_plan',
            'data': {
                'has_plan': True,
                'plan_id': plan['id'],
                'plan_title': plan['title'],
                'week_start': monday,
                'week_end': sunday,
                'total_activities': total_acts,
                'completed_activities': done_acts,
                'completion_pct': round(done_acts / total_acts * 100) if total_acts else 0,
                'total_planned_minutes': stats.get('mins') or 0,
            },
            'last_updated': now,
        }

    raise HTTPException(status_code=404, detail=f'Unknown widget: {widget_id}')


# ---------------------------------------------------------------------------
# Agent tools
# ---------------------------------------------------------------------------

@router.get('/agent/get_goals')
@router.post('/agent/get_goals')
def agent_get_goals(
    status: Optional[str] = None,
    body: Optional[dict] = None,
    token: TokenData = Depends(require_token),
) -> dict:
    """Get user's education goals."""
    user_id = token.user_id
    ph = _ph()
    filter_status = status or (body or {}).get('status', 'all')

    query = f'SELECT * FROM education_goals WHERE user_id = {ph} AND deleted_at IS NULL'
    params: list = [user_id]
    if filter_status == 'active':
        query += ' AND is_completed = 0'
    elif filter_status == 'completed':
        query += ' AND is_completed = 1'
    query += ' ORDER BY created_at DESC LIMIT 20'

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(query, params)
        rows = [dict(r) for r in cur.fetchall()]

    goals = [
        {
            'id': r['id'],
            'title': r['title'],
            'category': r['category'],
            'is_completed': bool(r['is_completed']),
            'target_date': r.get('target_date'),
            'created_at': str(r['created_at']),
        }
        for r in rows
    ]
    return {'success': True, 'result': {'goals': goals, 'total': len(goals)}}


@router.post('/agent/create_goal')
def agent_create_goal(
    body: dict,
    token: TokenData = Depends(require_token),
) -> dict:
    """Create a new education goal."""
    title = body.get('title')
    if not title:
        raise HTTPException(status_code=400, detail='title is required')

    ph = _ph()
    goal_id = str(uuid.uuid4())
    description = body.get('description', '')
    category = body.get('category', 'personal')
    target_date = body.get('target_date')
    user_id = token.user_id

    valid_categories = ('professional', 'personal', 'hobby', 'academic')
    if category not in valid_categories:
        category = 'personal'

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            f'INSERT INTO education_goals (id, user_id, title, description, category, target_date) '
            f'VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})',
            (goal_id, user_id, title, description, category, target_date),
        )
        conn.commit()

    return {
        'success': True,
        'result': {
            'id': goal_id,
            'title': title,
            'category': category,
            'target_date': target_date,
        },
        'message': f'Created goal: {title}',
    }


@router.get('/agent/get_weekly_plan')
@router.post('/agent/get_weekly_plan')
def agent_get_weekly_plan(
    week_start: Optional[str] = None,
    body: Optional[dict] = None,
    token: TokenData = Depends(require_token),
) -> dict:
    """Get the weekly study plan."""
    user_id = token.user_id
    ph = _ph()
    ws_str = week_start or (body or {}).get('week_start')
    monday = _normalize_to_monday(ws_str) if ws_str else _get_current_week_monday()
    sunday = (date_type.fromisoformat(monday) + timedelta(days=6)).isoformat()

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            f'SELECT * FROM weekly_plans WHERE user_id = {ph} AND week_start_date = {ph}',
            (user_id, monday),
        )
        plan_row = cur.fetchone()
        if not plan_row:
            return {
                'success': True,
                'result': {
                    'has_plan': False,
                    'week_start': monday,
                    'week_end': sunday,
                    'activities': [],
                },
            }

        plan = dict(plan_row)
        cur.execute(
            f'SELECT * FROM activities WHERE plan_id = {ph} ORDER BY scheduled_time ASC',
            (plan['id'],),
        )
        activities = [
            {
                'id': dict(r)['id'],
                'title': dict(r)['title'],
                'scheduled_time': str(dict(r)['scheduled_time']),
                'duration_minutes': dict(r)['duration_minutes'],
                'is_completed': bool(dict(r)['is_completed']),
                'goal_id': dict(r).get('goal_id'),
            }
            for r in cur.fetchall()
        ]

    total = len(activities)
    done = sum(1 for a in activities if a['is_completed'])
    return {
        'success': True,
        'result': {
            'has_plan': True,
            'plan_id': plan['id'],
            'plan_title': plan['title'],
            'week_start': monday,
            'week_end': sunday,
            'activities': activities,
            'total_activities': total,
            'completed_activities': done,
            'completion_pct': round(done / total * 100) if total else 0,
        },
    }


@router.post('/agent/add_activity')
def agent_add_activity(
    body: dict,
    token: TokenData = Depends(require_token),
) -> dict:
    """Schedule a study activity."""
    title = body.get('title')
    scheduled_time = body.get('scheduled_time')
    duration_minutes = body.get('duration_minutes')

    if not title:
        raise HTTPException(status_code=400, detail='title is required')
    if not scheduled_time:
        raise HTTPException(status_code=400, detail='scheduled_time is required')
    if not duration_minutes:
        raise HTTPException(status_code=400, detail='duration_minutes is required')

    user_id = token.user_id
    ph = _ph()

    # Determine which week this activity belongs to
    monday = _normalize_to_monday(scheduled_time)

    with get_db() as conn:
        plan = _get_or_create_plan_for_week(conn, user_id, monday)
        plan_id = plan['id']

        goal_id = body.get('goal_id')
        if goal_id:
            cur = get_cursor(conn)
            cur.execute(
                f'SELECT id FROM education_goals WHERE id = {ph} AND user_id = {ph} AND deleted_at IS NULL',
                (goal_id, user_id),
            )
            if not cur.fetchone():
                goal_id = None  # Silently drop invalid goal_id from agent calls

        activity_id = str(uuid.uuid4())
        cur = get_cursor(conn)
        cur.execute(
            f'INSERT INTO activities (id, plan_id, goal_id, title, description, duration_minutes, scheduled_time) '
            f'VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})',
            (activity_id, plan_id, goal_id, title,
             body.get('description'), int(duration_minutes), scheduled_time),
        )
        conn.commit()

    return {
        'success': True,
        'result': {
            'activity_id': activity_id,
            'plan_id': plan_id,
            'title': title,
            'scheduled_time': scheduled_time,
            'duration_minutes': int(duration_minutes),
        },
        'message': f'Scheduled "{title}" for {scheduled_time[:10]}',
    }


@router.post('/agent/complete_activity')
def agent_complete_activity(
    body: dict,
    token: TokenData = Depends(require_token),
) -> dict:
    """Mark a study activity as completed."""
    activity_id = body.get('activity_id')
    if not activity_id:
        raise HTTPException(status_code=400, detail='activity_id is required')

    user_id = token.user_id
    ph = _ph()
    now = datetime.now(timezone.utc).isoformat()
    actual_minutes = body.get('actual_minutes')

    with get_db() as conn:
        cur = get_cursor(conn)
        # Verify the activity belongs to a plan owned by this user
        cur.execute(
            f'SELECT a.id, a.title FROM activities a '
            f'JOIN weekly_plans p ON a.plan_id = p.id '
            f'WHERE a.id = {ph} AND p.user_id = {ph}',
            (activity_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Activity not found')

        activity_title = dict(row)['title']
        update_fields = ['is_completed = 1', f'completed_at = {ph}', f'updated_at = {ph}']
        params: list = [now, now]
        if actual_minutes is not None:
            update_fields.append(f'actual_minutes = {ph}')
            params.append(int(actual_minutes))
        params.append(activity_id)

        cur.execute(
            f'UPDATE activities SET {", ".join(update_fields)} WHERE id = {ph}',
            params,
        )
        conn.commit()

    return {
        'success': True,
        'result': {'activity_id': activity_id, 'is_completed': True},
        'message': f'Completed: {activity_title}',
    }


@router.get('/agent/get_weekly_summary')
@router.post('/agent/get_weekly_summary')
def agent_get_weekly_summary(
    week_start: Optional[str] = None,
    body: Optional[dict] = None,
    token: TokenData = Depends(require_token),
) -> dict:
    """Get completion summary for the week."""
    user_id = token.user_id
    ph = _ph()
    ws_str = week_start or (body or {}).get('week_start')
    monday = _normalize_to_monday(ws_str) if ws_str else _get_current_week_monday()
    sunday = (date_type.fromisoformat(monday) + timedelta(days=6)).isoformat()

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            f'SELECT id FROM weekly_plans WHERE user_id = {ph} AND week_start_date = {ph}',
            (user_id, monday),
        )
        plan_row = cur.fetchone()
        if not plan_row:
            return {
                'success': True,
                'result': {
                    'week_start': monday,
                    'week_end': sunday,
                    'total': 0,
                    'completed': 0,
                    'pending': 0,
                    'completion_pct': 0,
                    'total_planned_minutes': 0,
                    'total_completed_minutes': 0,
                },
            }

        plan_id = dict(plan_row)['id']
        cur.execute(
            f'SELECT COUNT(*) as total, SUM(is_completed) as done, '
            f'SUM(duration_minutes) as planned_mins, '
            f'SUM(CASE WHEN is_completed = 1 THEN duration_minutes ELSE 0 END) as done_mins '
            f'FROM activities WHERE plan_id = {ph}',
            (plan_id,),
        )
        stats = dict(cur.fetchone() or {})

    total = stats.get('total') or 0
    done = int(stats.get('done') or 0)
    return {
        'success': True,
        'result': {
            'week_start': monday,
            'week_end': sunday,
            'total': total,
            'completed': done,
            'pending': total - done,
            'completion_pct': round(done / total * 100) if total else 0,
            'total_planned_minutes': stats.get('planned_mins') or 0,
            'total_completed_minutes': stats.get('done_mins') or 0,
        },
    }


# ---------------------------------------------------------------------------
# Cross-module data endpoints
# ---------------------------------------------------------------------------

@router.get('/data/{data_id}')
def get_shared_data(
    data_id: str,
    token: TokenData = Depends(require_token),
) -> dict:
    """Return cross-module data."""
    user_id = token.user_id
    ph = _ph()
    today = date_type.today()

    if data_id == 'study_schedule':
        window_end = (today + timedelta(days=14)).isoformat()
        with get_db() as conn:
            cur = get_cursor(conn)
            cur.execute(
                f'SELECT a.id, a.title, a.scheduled_time, a.duration_minutes, a.is_completed, a.goal_id '
                f'FROM activities a '
                f'JOIN weekly_plans p ON a.plan_id = p.id '
                f'WHERE p.user_id = {ph} AND a.scheduled_time >= {ph} AND a.scheduled_time <= {ph} '
                f'ORDER BY a.scheduled_time ASC LIMIT 50',
                (user_id, today.isoformat(), window_end),
            )
            activities = [
                {
                    'id': dict(r)['id'],
                    'title': dict(r)['title'],
                    'scheduled_time': str(dict(r)['scheduled_time']),
                    'duration_minutes': dict(r)['duration_minutes'],
                    'is_completed': bool(dict(r)['is_completed']),
                    'goal_id': dict(r).get('goal_id'),
                }
                for r in cur.fetchall()
            ]
        return {
            'data_id': 'study_schedule',
            'data': {
                'activities': activities,
                'date_range': {'start': today.isoformat(), 'end': window_end},
            },
        }

    elif data_id == 'goals_progress':
        with get_db() as conn:
            cur = get_cursor(conn)
            cur.execute(
                f'SELECT id, title, category, is_completed, target_date FROM education_goals '
                f'WHERE user_id = {ph} AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 20',
                (user_id,),
            )
            goals = [dict(r) for r in cur.fetchall()]
            active = sum(1 for g in goals if not g['is_completed'])
            completed = sum(1 for g in goals if g['is_completed'])

        return {
            'data_id': 'goals_progress',
            'data': {
                'goals': [
                    {
                        'id': g['id'],
                        'title': g['title'],
                        'category': g['category'],
                        'is_completed': bool(g['is_completed']),
                        'target_date': g.get('target_date'),
                    }
                    for g in goals
                ],
                'total_active': active,
                'total_completed': completed,
            },
        }

    raise HTTPException(status_code=404, detail=f'Unknown data_id: {data_id}')


# ---------------------------------------------------------------------------
# Summary (optional contract endpoint)
# ---------------------------------------------------------------------------

@router.get('/summary')
def get_summary(token: TokenData = Depends(require_token)) -> dict:
    """Return a natural language education progress summary for AI briefings."""
    user_id = token.user_id
    ph = _ph()
    today = date_type.today()
    monday = (today - timedelta(days=today.weekday())).isoformat()

    with get_db() as conn:
        cur = get_cursor(conn)

        # Active goal count
        cur.execute(
            f'SELECT COUNT(*) as cnt FROM education_goals '
            f'WHERE user_id = {ph} AND is_completed = 0 AND deleted_at IS NULL',
            (user_id,),
        )
        active_goals = dict(cur.fetchone()).get('cnt', 0)

        # This week's plan
        cur.execute(
            f'SELECT id FROM weekly_plans WHERE user_id = {ph} AND week_start_date = {ph}',
            (user_id, monday),
        )
        plan_row = cur.fetchone()
        total_acts, done_acts = 0, 0
        if plan_row:
            plan_id = dict(plan_row)['id']
            cur.execute(
                f'SELECT COUNT(*) as total, SUM(is_completed) as done FROM activities WHERE plan_id = {ph}',
                (plan_id,),
            )
            stats = dict(cur.fetchone() or {})
            total_acts = stats.get('total') or 0
            done_acts = int(stats.get('done') or 0)

    parts = [f'{active_goals} active learning goal{"s" if active_goals != 1 else ""}.']
    if total_acts:
        pct = round(done_acts / total_acts * 100) if total_acts else 0
        parts.append(f'This week: {done_acts}/{total_acts} activities completed ({pct}%).')
    else:
        parts.append('No activities scheduled this week.')

    return {
        'module_id': 'education-planner',
        'summary': ' '.join(parts),
        'data': {
            'date': today.isoformat(),
            'active_goals': active_goals,
            'this_week_total': total_acts,
            'this_week_completed': done_acts,
            'this_week_completion_pct': round(done_acts / total_acts * 100) if total_acts else 0,
        },
    }


# ---------------------------------------------------------------------------
# Calendar (optional contract endpoint)
# ---------------------------------------------------------------------------

@router.get('/calendar')
def get_calendar(token: TokenData = Depends(require_token)) -> dict:
    """Return upcoming study activities as calendar events (next 14 days)."""
    user_id = token.user_id
    ph = _ph()
    today = date_type.today()
    window_end = (today + timedelta(days=14)).isoformat()

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            f'SELECT a.id, a.title, a.scheduled_time, a.duration_minutes, a.is_completed, g.title as goal_title '
            f'FROM activities a '
            f'JOIN weekly_plans p ON a.plan_id = p.id '
            f'LEFT JOIN education_goals g ON a.goal_id = g.id '
            f'WHERE p.user_id = {ph} AND a.scheduled_time >= {ph} AND a.scheduled_time <= {ph} '
            f'ORDER BY a.scheduled_time ASC LIMIT 30',
            (user_id, today.isoformat(), window_end),
        )
        rows = cur.fetchall()

    events = [
        {
            'id': dict(r)['id'],
            'title': dict(r)['title'],
            'date': str(dict(r)['scheduled_time'])[:10],
            'time': str(dict(r)['scheduled_time'])[11:16] if len(str(dict(r)['scheduled_time'])) > 10 else None,
            'type': 'study',
            'duration_minutes': dict(r)['duration_minutes'],
            'is_completed': bool(dict(r)['is_completed']),
            'goal_title': dict(r).get('goal_title'),
            'priority': 'medium',
        }
        for r in rows
    ]

    return {
        'module_id': 'education-planner',
        'events': events,
        'window_days': 14,
    }
