"""Artemis Module Contract endpoints — stub implementation.

Full implementation comes in Phase 2. These endpoints must exist for
Artemis discovery; they return minimal but valid responses.
"""

from fastapi import APIRouter, Depends
from routers.auth import get_current_user
from core.auth_service import TokenData

router = APIRouter(prefix='/artemis', tags=['artemis'])

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


@router.get('/widgets/{widget_id}')
async def get_widget(
    widget_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Return live widget data. Full implementation in Phase 2."""
    return {'widget_id': widget_id, 'data': {}, 'status': 'stub — Phase 2'}


@router.post('/agent/{tool_id}')
async def execute_agent_tool(
    tool_id: str,
    body: dict,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Execute an agent tool. Full implementation in Phase 2."""
    return {'tool_id': tool_id, 'success': False, 'message': 'stub — Phase 2'}


@router.get('/data/{data_id}')
async def get_shared_data(
    data_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Return cross-module data. Full implementation in Phase 2."""
    return {'data_id': data_id, 'data': {}, 'status': 'stub — Phase 2'}
