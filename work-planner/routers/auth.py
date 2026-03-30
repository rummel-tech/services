"""Authentication router — register, login, refresh, logout, me."""

import os
import uuid
import time
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.auth_service import (
    Token, TokenData, UserCreate, UserLogin, User,
    get_password_hash, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from core.database import get_db, get_cursor
from core.logging_config import get_logger
from core import metrics
from core.redis_client import blacklist_token, is_token_blacklisted
from core.settings import get_settings

log = get_logger('api.auth')
settings = get_settings()

if settings.environment == 'production':
    limiter = Limiter(key_func=get_remote_address)
    REGISTER_LIMIT = '5/minute'
    LOGIN_LIMIT = '10/minute'
    REFRESH_LIMIT = '10/minute'
    LOGOUT_LIMIT = '20/minute'
else:
    limiter = Limiter(key_func=get_remote_address, default_limits=['10000 per minute'])
    REGISTER_LIMIT = '10000/minute'
    LOGIN_LIMIT = '10000/minute'
    REFRESH_LIMIT = '10000/minute'
    LOGOUT_LIMIT = '10000/minute'

router = APIRouter(prefix='/auth', tags=['authentication'])
security = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> TokenData:
    """Validate JWT and return token data. Supports dev bypass and Artemis tokens."""
    settings = get_settings()
    disable_auth_env = os.getenv('DISABLE_AUTH', '').lower() == 'true'

    if (settings.disable_auth or disable_auth_env) and settings.environment == 'development' and credentials is None:
        log.info('auth_bypassed_dev_mode', extra={'stub_user': 'user-123'})
        return TokenData(user_id='user-123', email='dev@example.com', jti='dev-stub', exp=None)

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Not authenticated',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    token_data = decode_token(credentials.credentials)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid authentication credentials',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    if token_data.jti and is_token_blacklisted(token_data.jti):
        log.warning('auth_token_blacklisted', extra={'jti': token_data.jti})
        metrics.record_domain_event('auth_token_blacklisted')
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Token has been revoked',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    return token_data


def get_admin_user(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Require admin role."""
    settings = get_settings()
    if settings.disable_auth and settings.environment == 'development':
        return current_user
    user = _get_user_by_id(current_user.user_id)
    if not user or not user.get('is_admin'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin access required')
    return current_user


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_user_by_email(email: str) -> Optional[dict]:
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT * FROM users WHERE LOWER(email) = LOWER(?)', (email,))
        row = cur.fetchone()
        return dict(row) if row else None


def _get_user_by_id(user_id: str) -> Optional[dict]:
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def _create_user(user: UserCreate, registration_code: str) -> dict:
    user_id = str(uuid.uuid4())
    hashed = get_password_hash(user.password)
    email = user.email.lower()
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            'INSERT INTO users (id, email, hashed_password, full_name) VALUES (?, ?, ?, ?)',
            (user_id, email, hashed, user.full_name),
        )
        cur.execute(
            'UPDATE registration_codes SET is_used = 1, used_by_user_id = ? WHERE code = ?',
            (user_id, registration_code),
        )
        conn.commit()
    return _get_user_by_id(user_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post('/validate-code')
@limiter.limit(LOGIN_LIMIT)
async def validate_registration_code(request: Request, code: str) -> dict:
    """Check whether a registration code is valid (without consuming it)."""
    if not code or len(code) < 4:
        return {'valid': False, 'message': 'Invalid code format'}
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """SELECT code FROM registration_codes
               WHERE code = ? AND is_used = 0
               AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)""",
            (code.upper(),),
        )
        row = cur.fetchone()
    if row:
        return {'valid': True, 'message': 'Code is valid'}
    return {'valid': False, 'message': 'Invalid or expired code'}


@router.post('/register', status_code=status.HTTP_201_CREATED)
@limiter.limit(REGISTER_LIMIT)
async def register(request: Request, user: UserCreate) -> dict:
    """Register a new user account, or add to waitlist if no valid code supplied."""
    if _get_user_by_email(user.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Email already registered')

    if not user.registration_code:
        with get_db() as conn:
            cur = get_cursor(conn)
            try:
                cur.execute('INSERT INTO waitlist (email) VALUES (?)', (user.email,))
                conn.commit()
            except Exception:
                pass
        return {'status': 'waitlisted', 'message': "You've been added to the waiting list."}

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """SELECT code FROM registration_codes
               WHERE code = ? AND is_used = 0
               AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)""",
            (user.registration_code,),
        )
        code_row = cur.fetchone()

    if not code_row:
        with get_db() as conn:
            cur = get_cursor(conn)
            try:
                cur.execute('INSERT INTO waitlist (email) VALUES (?)', (user.email,))
                conn.commit()
            except Exception:
                pass
        return {'status': 'waitlisted', 'message': 'Invalid or used code. Added to waiting list.'}

    db_user = _create_user(user, user.registration_code)
    access_token = create_access_token({'sub': db_user['id'], 'email': db_user['email']})
    refresh_token = create_refresh_token({'sub': db_user['id'], 'email': db_user['email']})
    log.info('auth_register_success', extra={'user_id': db_user['id']})
    metrics.record_domain_event('auth_register_success')
    return {'status': 'registered', 'access_token': access_token, 'refresh_token': refresh_token, 'token_type': 'bearer'}


@router.post('/login', response_model=Token)
@limiter.limit(LOGIN_LIMIT)
async def login(request: Request, credentials: UserLogin) -> Token:
    """Authenticate and return JWT tokens."""
    user = _get_user_by_email(credentials.email)
    if not user or not verify_password(credentials.password, user['hashed_password']):
        log.warning('auth_login_failed', extra={'email': credentials.email})
        metrics.record_domain_event('auth_login_failed')
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Incorrect email or password')

    if not user['is_active']:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Account is inactive')

    access_token = create_access_token({'sub': user['id'], 'email': user['email']})
    refresh_token = create_refresh_token({'sub': user['id'], 'email': user['email']})
    log.info('auth_login_success', extra={'user_id': user['id']})
    metrics.record_domain_event('auth_login_success')
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post('/refresh', response_model=Token)
@limiter.limit(REFRESH_LIMIT)
async def refresh(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Token:
    """Exchange a refresh token for a new token pair."""
    token_data = decode_token(credentials.credentials)
    if token_data is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid refresh token')

    user = _get_user_by_id(token_data.user_id)
    if not user or not user['is_active']:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User not found or inactive')

    access_token = create_access_token({'sub': user['id'], 'email': user['email']})
    new_refresh = create_refresh_token({'sub': user['id'], 'email': user['email']})
    log.info('auth_refresh_success', extra={'user_id': user['id']})
    metrics.record_domain_event('auth_refresh_success')
    return Token(access_token=access_token, refresh_token=new_refresh)


@router.get('/me', response_model=User)
async def me(current_user: TokenData = Depends(get_current_user)) -> User:
    """Return current authenticated user's profile."""
    user = _get_user_by_id(current_user.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
    return User(
        id=user['id'],
        email=user['email'],
        full_name=user.get('full_name'),
        is_active=bool(user['is_active']),
        created_at=user['created_at'],
    )


@router.post('/logout')
@limiter.limit(LOGOUT_LIMIT)
async def logout(request: Request, current_user: TokenData = Depends(get_current_user)) -> dict:
    """Logout and blacklist the current token."""
    if current_user.jti and current_user.exp:
        now = int(time.time())
        ttl = max(current_user.exp - now, 60)
        blacklist_token(current_user.jti, ttl)
    log.info('auth_logout', extra={'user_id': current_user.user_id})
    metrics.record_domain_event('auth_logout')
    return {'message': 'Successfully logged out'}


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@router.post('/admin/codes', status_code=status.HTTP_201_CREATED)
async def create_registration_code(
    current_user: TokenData = Depends(get_admin_user),
    expires_days: Optional[int] = None,
) -> dict:
    """Generate a new registration code (admin only)."""
    import random
    import string
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    expires_at = None
    if expires_days:
        from datetime import timedelta
        expires_at = (datetime.utcnow() + timedelta(days=expires_days)).isoformat()
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            'INSERT INTO registration_codes (code, expires_at) VALUES (?, ?)',
            (code, expires_at),
        )
        conn.commit()
    return {'code': code, 'expires_at': expires_at}


@router.get('/admin/codes')
async def list_registration_codes(
    current_user: TokenData = Depends(get_admin_user),
    show_used: bool = False,
) -> dict:
    """List registration codes (admin only)."""
    with get_db() as conn:
        cur = get_cursor(conn)
        if show_used:
            cur.execute('SELECT * FROM registration_codes ORDER BY created_at DESC')
        else:
            cur.execute('SELECT * FROM registration_codes WHERE is_used = 0 ORDER BY created_at DESC')
        rows = cur.fetchall()
    return {'codes': [dict(r) for r in rows]}
