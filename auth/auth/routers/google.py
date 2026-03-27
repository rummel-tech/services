"""Google OAuth router.

Flow:
  1. Flutter app authenticates with Google and gets an ID token.
  2. Flutter POSTs the ID token to POST /auth/google.
  3. This service verifies the token with Google, finds or creates the user,
     and returns an Artemis JWT pair.
"""
import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel

from auth.core.database import get_cursor, get_db
from auth.core.jwt_service import create_access_token, create_refresh_token
from auth.core.settings import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleTokenRequest(BaseModel):
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def _get_user_by_google_id(google_id: str) -> Optional[dict]:
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("SELECT * FROM users WHERE google_id = ?", (google_id,))
        row = cur.fetchone()
        return dict(row) if row else None


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


@router.post("/google", response_model=TokenResponse)
async def google_sign_in(body: GoogleTokenRequest):
    settings = get_settings()

    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    # Verify the Google ID token
    try:
        id_info = google_id_token.verify_oauth2_token(
            body.id_token,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {e}")

    google_id = id_info["sub"]
    email = id_info.get("email", "").lower()
    name = id_info.get("name", "")

    # Find existing user by Google ID
    user = _get_user_by_google_id(google_id)

    if not user:
        # Try to link to an existing email account
        user = _get_user_by_email(email)
        if user:
            # Link Google ID to existing account
            with get_db() as conn:
                cur = get_cursor(conn)
                cur.execute(
                    "UPDATE users SET google_id = ?, full_name = COALESCE(full_name, ?) WHERE id = ?",
                    (google_id, name, user["id"]),
                )
                conn.commit()
            user = _get_user_by_id(user["id"])
        else:
            # Create new user
            user_id = str(uuid.uuid4())
            with get_db() as conn:
                cur = get_cursor(conn)
                cur.execute(
                    """INSERT INTO users (id, email, full_name, google_id)
                       VALUES (?, ?, ?, ?)""",
                    (user_id, email, name, google_id),
                )
                conn.commit()
            user = _get_user_by_id(user_id)

    if not user or not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account is inactive")

    modules = json.loads(user.get("enabled_modules") or "[]")
    permissions = json.loads(user.get("permissions") or "[]")

    access = create_access_token(
        user_id=user["id"],
        email=user["email"],
        name=user.get("full_name") or name,
        modules=modules,
        permissions=permissions,
    )
    refresh = create_refresh_token(user_id=user["id"], email=user["email"])
    return TokenResponse(access_token=access, refresh_token=refresh)
