"""
Authentication for the Trip Planner service.

Provides a ``TokenData`` model and ``decode_token`` function for standalone
HS256 JWT validation.  Artemis platform tokens (RS256) are handled by the
shared ``common.artemis_auth`` module — see ``routers/artemis.py``.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Header, HTTPException

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class TokenData:
    user_id: str
    email: str = ""
    jti: Optional[str] = None
    exp: Optional[int] = None


def decode_token(raw: str) -> Optional[TokenData]:
    """Decode a standalone HS256 JWT. Returns None on failure."""
    try:
        payload = jwt.decode(raw, settings.jwt_secret, algorithms=["HS256"])
        return TokenData(
            user_id=payload.get("sub") or payload.get("user_id", ""),
            email=payload.get("email", ""),
            jti=payload.get("jti"),
            exp=payload.get("exp"),
        )
    except jwt.ExpiredSignatureError:
        return None
    except jwt.PyJWTError:
        return None


async def require_token(authorization: str = Header(...)) -> TokenData:
    """FastAPI dependency — validates bearer token, returns TokenData."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    raw = authorization.removeprefix("Bearer ").strip()

    if settings.environment != "production" and getattr(settings, "disable_auth", False):
        return TokenData(user_id="dev-user", email="dev@local")

    token_data = decode_token(raw)
    if token_data:
        return token_data

    if settings.environment != "production":
        logger.warning("Auth unavailable — using dev stub user")
        return TokenData(user_id="dev-user", email="dev@local")

    raise HTTPException(status_code=401, detail="Invalid token")
