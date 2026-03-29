"""Shared token auth — used by both native and Artemis endpoints."""
import os
import time
from typing import Optional

import httpx
from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel

ARTEMIS_AUTH_URL = os.getenv("ARTEMIS_AUTH_URL", "http://localhost:8090")
_artemis_public_key: Optional[str] = None
_artemis_public_key_fetched_at: float = 0.0
_KEY_CACHE_TTL = 86400  # 24 hours


class TokenData(BaseModel):
    user_id: str
    email: str = ""


def _fetch_public_key() -> Optional[str]:
    global _artemis_public_key, _artemis_public_key_fetched_at
    now = time.time()
    if _artemis_public_key and (now - _artemis_public_key_fetched_at) < _KEY_CACHE_TTL:
        return _artemis_public_key
    try:
        r = httpx.get(f"{ARTEMIS_AUTH_URL}/auth/public-key", timeout=3.0)
        if r.status_code == 200:
            _artemis_public_key = r.json()["public_key"]
            _artemis_public_key_fetched_at = now
            return _artemis_public_key
    except Exception:
        pass
    return None


def require_token(authorization: Optional[str] = Header(None)) -> TokenData:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    raw = authorization.split(" ", 1)[1]
    try:
        unverified = jwt.get_unverified_claims(raw)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if unverified.get("iss") == "artemis-auth":
        pub_key = _fetch_public_key()
        if pub_key:
            try:
                payload = jwt.decode(raw, pub_key, algorithms=["RS256"], issuer="artemis-auth")
                return TokenData(user_id=payload["sub"], email=payload.get("email", ""))
            except JWTError as e:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
        if os.getenv("ENVIRONMENT", "development") != "production":
            return TokenData(user_id=unverified.get("sub", "dev-user"), email=unverified.get("email", ""))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service unavailable")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported token issuer")
