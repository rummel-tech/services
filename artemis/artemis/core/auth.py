"""Token validation for the Artemis platform.

Fetches the RSA public key from the auth service on first use, then caches
it for all subsequent validations.
"""
import logging
from typing import Optional

import httpx
from fastapi import Header, HTTPException, status
from jose import JWTError, jwt

from artemis.core.settings import get_settings

log = logging.getLogger("artemis.auth")

_public_key: Optional[str] = None


async def fetch_public_key() -> Optional[str]:
    global _public_key
    if _public_key:
        return _public_key
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{settings.artemis_auth_url}/auth/public-key")
            if r.status_code == 200:
                _public_key = r.json()["public_key"]
                log.info("artemis public key cached")
                return _public_key
    except Exception as e:
        log.warning(f"could not fetch auth public key: {e}")
    return None


def reset_public_key_cache() -> None:
    """Force re-fetch on next validation (useful for key rotation)."""
    global _public_key
    _public_key = None


async def validate_token(authorization: Optional[str] = Header(None)) -> dict:
    """FastAPI dependency — validates an Artemis Bearer token.

    Returns the decoded JWT payload on success.
    Raises 401 on missing/invalid token, 503 if auth service is unreachable.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    raw = authorization.split(" ", 1)[1]

    pub_key = await fetch_public_key()
    if not pub_key:
        settings = get_settings()
        if settings.environment != "production":
            # Dev fallback — decode without verification
            log.warning("auth service unavailable — decoding token without signature verification")
            try:
                return jwt.get_unverified_claims(raw)
            except JWTError:
                raise HTTPException(status_code=401, detail="Invalid token")
        raise HTTPException(status_code=503, detail="Auth service unavailable")

    try:
        return jwt.decode(raw, pub_key, algorithms=["RS256"], issuer="artemis-auth")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
