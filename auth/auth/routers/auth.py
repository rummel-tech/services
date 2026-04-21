"""Auth router: register, login, refresh, logout, me."""
import json
import time
import uuid
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address

from auth.core.audit import log_event
from auth.core.database import get_cursor, get_db
from auth.core.jwt_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from auth.core.redis_client import blacklist_token, is_token_blacklisted
from auth.core.settings import get_settings

settings = get_settings()

if settings.environment == "production":
    limiter = Limiter(key_func=get_remote_address)
    REGISTER_LIMIT = "5/minute"
    LOGIN_LIMIT = "10/minute"
    REFRESH_LIMIT = "10/minute"
    LOGOUT_LIMIT = "20/minute"
else:
    limiter = Limiter(key_func=get_remote_address, default_limits=["10000 per minute"])
    REGISTER_LIMIT = LOGIN_LIMIT = REFRESH_LIMIT = LOGOUT_LIMIT = "10000/minute"

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


# --- Pydantic models ---

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    is_active: bool
    enabled_modules: list[str]
    permissions: list[str]


# --- Helpers ---

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def _get_user_by_email(email: str) -> Optional[dict]:
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email,))
        row = cur.fetchone()
        return dict(row) if row else None


def _get_user_by_id(user_id: str) -> Optional[dict]:
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def _issue_token_pair(user: dict) -> TokenResponse:
    modules = json.loads(user.get("enabled_modules") or "[]")
    permissions = json.loads(user.get("permissions") or "[]")
    access = create_access_token(
        user_id=user["id"],
        email=user["email"],
        name=user.get("full_name") or "",
        modules=modules,
        permissions=permissions,
    )
    refresh = create_refresh_token(user_id=user["id"], email=user["email"])
    return TokenResponse(access_token=access, refresh_token=refresh)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    jti = payload.get("jti")
    if jti and is_token_blacklisted(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    user = _get_user_by_id(payload["sub"])
    if not user or not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


# --- Endpoints ---

@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit(REGISTER_LIMIT)
async def register(request: Request, body: UserRegister):
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    if _get_user_by_email(body.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid.uuid4())
    hashed = _hash_password(body.password)

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """INSERT INTO users (id, email, hashed_password, full_name)
               VALUES (?, ?, ?, ?)""",
            (user_id, body.email.lower(), hashed, body.full_name),
        )
        conn.commit()

    user = _get_user_by_id(user_id)
    log_event("register", request, user_id=user_id)
    return _issue_token_pair(user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(LOGIN_LIMIT)
async def login(request: Request, body: UserLogin):
    user = _get_user_by_email(body.email)
    if not user or not user.get("hashed_password"):
        log_event("login_failed", request, metadata={"email": body.email, "reason": "invalid_credentials"})
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if not _verify_password(body.password, user["hashed_password"]):
        log_event("login_failed", request, metadata={"email": body.email, "reason": "invalid_credentials"})
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account is inactive")

    log_event("login_success", request, user_id=user["id"])
    return _issue_token_pair(user)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(REFRESH_LIMIT)
async def refresh(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing token")

    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = _get_user_by_id(payload["sub"])
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    log_event("token_refresh", request, user_id=user["id"])
    return _issue_token_pair(user)


@router.post("/logout")
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing token")

    payload = decode_token(credentials.credentials)
    user_id = None
    if payload:
        user_id = payload.get("sub")
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            ttl = max(int(exp) - int(time.time()), 60)
            blacklist_token(jti, ttl)

    log_event("logout", request, user_id=user_id)
    return {"message": "Logged out"}


@router.get("/me", response_model=UserOut)
async def me(current_user: dict = Depends(get_current_user)):
    return UserOut(
        id=current_user["id"],
        email=current_user["email"],
        full_name=current_user.get("full_name"),
        is_active=bool(current_user["is_active"]),
        enabled_modules=json.loads(current_user.get("enabled_modules") or "[]"),
        permissions=json.loads(current_user.get("permissions") or "[]"),
    )


@router.get("/me/data")
async def export_my_data(request: Request, current_user: dict = Depends(get_current_user)):
    """GDPR Article 20 — export all personal data held for the authenticated user."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            "SELECT id, user_id, expires_at, created_at FROM refresh_tokens WHERE user_id = ?",
            (current_user["id"],),
        )
        tokens = [dict(row) for row in cur.fetchall()]

    log_event("gdpr_export", request, user_id=current_user["id"])
    return {
        "exported_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "user": {
            "id": current_user["id"],
            "email": current_user["email"],
            "full_name": current_user.get("full_name"),
            "google_id": current_user.get("google_id"),
            "is_active": bool(current_user["is_active"]),
            "is_admin": bool(current_user.get("is_admin")),
            "enabled_modules": json.loads(current_user.get("enabled_modules") or "[]"),
            "permissions": json.loads(current_user.get("permissions") or "[]"),
            "created_at": current_user.get("created_at"),
            "updated_at": current_user.get("updated_at"),
        },
        "refresh_tokens": tokens,
    }


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    current_user: dict = Depends(get_current_user),
):
    """GDPR Article 17 — right to erasure. Permanently deletes the account and all tokens."""
    user_id = current_user["id"]

    # Blacklist current token so it can't be reused
    if credentials:
        payload = decode_token(credentials.credentials)
        if payload:
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                ttl = max(int(exp) - int(time.time()), 60)
                blacklist_token(jti, ttl)

    log_event("gdpr_delete", request, user_id=user_id)
    with get_db() as conn:
        cur = get_cursor(conn)
        # refresh_tokens cascade-delete with users FK
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()


@router.get("/audit-log")
async def get_audit_log(
    limit: int = 100,
    event: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Return audit log entries. Admin only."""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    with get_db() as conn:
        cur = get_cursor(conn)
        if event:
            cur.execute(
                "SELECT * FROM audit_logs WHERE event = ? ORDER BY created_at DESC LIMIT ?",
                (event, limit),
            )
        else:
            cur.execute(
                "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        rows = cur.fetchall()

    return [dict(r) for r in rows]
