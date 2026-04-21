"""Shared dual-mode authentication for Artemis module endpoints.

Every backend service that acts as an Artemis module needs to accept
**both** its own standalone JWT tokens AND Artemis platform tokens
(``iss == "artemis-auth"``).  This module provides the shared logic so
individual services don't need to duplicate the public-key-fetching and
dual-verification flow.

Usage in a service's ``routers/artemis.py``::

    from common.artemis_auth import create_artemis_token_dependency

    # Pass your service's own token decoder so standalone tokens still work.
    require_token = create_artemis_token_dependency(
        standalone_decoder=decode_token,   # your service's existing decoder
        token_data_class=TokenData,        # your service's TokenData type
    )

    @router.get("/widgets/{widget_id}")
    def get_widget(widget_id: str, token: TokenData = Depends(require_token)):
        ...
"""

import os
import time
import logging
from typing import Any, Callable, Optional, Type

from fastapi import Header, HTTPException, status

log = logging.getLogger("common.artemis_auth")

# ---------------------------------------------------------------------------
# Artemis public key cache (shared across all routers in the process)
# ---------------------------------------------------------------------------

_artemis_public_key: Optional[str] = None
_artemis_public_key_fetched_at: float = 0.0
_KEY_CACHE_TTL = 86400  # 24 hours


def get_artemis_auth_url() -> str:
    return os.getenv("ARTEMIS_AUTH_URL", "http://localhost:8090")


def fetch_artemis_public_key(*, force: bool = False) -> Optional[str]:
    """Fetch the Artemis RSA public key from the auth service, with 24h cache."""
    global _artemis_public_key, _artemis_public_key_fetched_at

    now = time.time()
    if not force and _artemis_public_key and (now - _artemis_public_key_fetched_at) < _KEY_CACHE_TTL:
        return _artemis_public_key

    try:
        import httpx
        url = f"{get_artemis_auth_url()}/auth/public-key"
        r = httpx.get(url, timeout=3.0)
        if r.status_code == 200:
            data = r.json()
            _artemis_public_key = data.get("public_key") or data
            _artemis_public_key_fetched_at = now
            return _artemis_public_key
    except Exception:
        log.warning("artemis_public_key_fetch_failed", extra={"url": get_artemis_auth_url()})
    return None


def _decode_artemis_token(raw: str, *, environment: str = "development") -> Any:
    """Verify an ``iss=artemis-auth`` RS256 token and return a dict of claims.

    Returns a plain dict with at least ``sub`` and ``email`` keys.
    Raises HTTPException on failure.
    """
    from jose import JWTError, jwt

    pub_key = fetch_artemis_public_key()
    if pub_key:
        try:
            payload = jwt.decode(raw, pub_key, algorithms=["RS256"], issuer="artemis-auth")
            return {
                "user_id": payload["sub"],
                "email": payload.get("email", ""),
                "jti": payload.get("jti"),
                "exp": payload.get("exp"),
                "permissions": payload.get("permissions", []),
                "modules": payload.get("modules", []),
            }
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid Artemis token: {e}",
            )

    # Auth service unavailable — allow dev-mode stub
    if environment != "production":
        from jose import jwt as _jwt
        try:
            unverified = _jwt.get_unverified_claims(raw)
        except Exception:
            unverified = {}
        log.warning("artemis_auth_unavailable_dev_stub")
        return {
            "user_id": unverified.get("sub", "dev-user"),
            "email": unverified.get("email", ""),
            "permissions": unverified.get("permissions", []),
            "modules": unverified.get("modules", []),
        }

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Auth service unavailable",
    )


def create_artemis_token_dependency(
    *,
    standalone_decoder: Callable[[str], Any],
    token_data_class: Type,
    environment: Optional[str] = None,
):
    """Build a FastAPI ``Depends`` callable that accepts both token types.

    Args:
        standalone_decoder: Service's existing function that takes a raw JWT
            string and returns a ``token_data_class`` instance (or ``None``
            on failure).
        token_data_class: The dataclass/model to instantiate from decoded
            claims (must accept ``user_id``, ``email``, and optionally
            ``jti``/``exp`` kwargs).
        environment: Override environment (defaults to ``ENVIRONMENT`` env var).
    """
    env = environment or os.getenv("ENVIRONMENT", "development")

    def require_token(authorization: Optional[str] = Header(None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing token",
            )
        raw = authorization.split(" ", 1)[1]

        # Peek at issuer without verifying signature
        try:
            from jose import jwt
            unverified = jwt.get_unverified_claims(raw)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        if unverified.get("iss") == "artemis-auth":
            claims = _decode_artemis_token(raw, environment=env)
            try:
                return token_data_class(
                    user_id=claims["user_id"],
                    email=claims["email"],
                    jti=claims.get("jti"),
                    exp=claims.get("exp"),
                    permissions=claims.get("permissions", []),
                    modules=claims.get("modules", []),
                )
            except TypeError:
                # token_data_class doesn't accept permissions/modules — fall back
                return token_data_class(
                    user_id=claims["user_id"],
                    email=claims["email"],
                    jti=claims.get("jti"),
                    exp=claims.get("exp"),
                )

        # Standalone token — delegate to the service's own decoder
        token_data = standalone_decoder(raw)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        return token_data

    return require_token
