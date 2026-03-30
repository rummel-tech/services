"""Artemis Module Contract endpoints — stub implementation.

Full implementation comes in Phase 2. These endpoints must exist for
Artemis discovery; they return minimal but valid responses.

Accepts both standalone work-planner tokens AND Artemis platform tokens
(iss == "artemis-auth"). Artemis tokens are verified against the public key
fetched from the auth service at ARTEMIS_AUTH_URL.
"""

import os
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from jose import JWTError, jwt

from core.auth_service import TokenData, decode_token
from core.settings import get_settings

router = APIRouter(prefix='/artemis', tags=['artemis'])

# ---------------------------------------------------------------------------
# Artemis public key cache (TTL: 24 hours)
# ---------------------------------------------------------------------------

_artemis_public_key: Optional[str] = None
_artemis_public_key_fetched_at: float = 0.0
_KEY_CACHE_TTL = 86400  # 24 hours

ARTEMIS_AUTH_URL = os.getenv('ARTEMIS_AUTH_URL', 'http://localhost:8090')


def _fetch_artemis_public_key() -> Optional[str]:
    """Fetch and cache the Artemis RSA public key from the auth service."""
    global _artemis_public_key, _artemis_public_key_fetched_at
    now = time.time()
    if _artemis_public_key and (now - _artemis_public_key_fetched_at) < _KEY_CACHE_TTL:
        return _artemis_public_key
    try:
        r = httpx.get(f'{ARTEMIS_AUTH_URL}/auth/public-key', timeout=3.0)
        if r.status_code == 200:
            _artemis_public_key = r.json()['public_key']
            _artemis_public_key_fetched_at = now
            return _artemis_public_key
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Dual-mode token dependency
# ---------------------------------------------------------------------------

def _get_token_payload(authorization: Optional[str]) -> TokenData:
    """Accept both standalone work-planner tokens and Artemis platform tokens."""
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Missing token')

    raw = authorization.split(' ', 1)[1]

    try:
        unverified = jwt.get_unverified_claims(raw)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')

    if unverified.get('iss') == 'artemis-auth':
        pub_key = _fetch_artemis_public_key()
        if pub_key:
            try:
                payload = jwt.decode(raw, pub_key, algorithms=['RS256'], issuer='artemis-auth')
                return TokenData(
                    user_id=payload['sub'],
                    email=payload.get('email', ''),
                    jti=payload.get('jti'),
                    exp=payload.get('exp'),
                )
            except JWTError as e:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f'Invalid Artemis token: {e}')
        # Auth service unavailable — dev fallback only
        settings = get_settings()
        if settings.environment != 'production':
            return TokenData(user_id=unverified.get('sub', 'dev-user'), email=unverified.get('email', ''))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Auth service unavailable')

    # Standalone token
    token_data = decode_token(raw)
    if not token_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')
    return token_data


def require_token(authorization: Optional[str] = Header(None)) -> TokenData:
    return _get_token_payload(authorization)


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


@router.get('/widgets/{widget_id}')
async def get_widget(
    widget_id: str,
    token: TokenData = Depends(require_token),
) -> dict:
    """Return live widget data. Full implementation in Phase 2."""
    return {'widget_id': widget_id, 'data': {}, 'status': 'stub — Phase 2'}


@router.post('/agent/{tool_id}')
async def execute_agent_tool(
    tool_id: str,
    body: dict,
    token: TokenData = Depends(require_token),
) -> dict:
    """Execute an agent tool. Full implementation in Phase 2."""
    return {'tool_id': tool_id, 'success': False, 'message': 'stub — Phase 2'}


@router.get('/data/{data_id}')
async def get_shared_data(
    data_id: str,
    token: TokenData = Depends(require_token),
) -> dict:
    """Return cross-module data. Full implementation in Phase 2."""
    return {'data_id': data_id, 'data': {}, 'status': 'stub — Phase 2'}
