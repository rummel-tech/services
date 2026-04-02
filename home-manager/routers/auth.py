"""Shared token auth — used by both native and Artemis endpoints.

Home Manager only accepts Artemis platform tokens (standalone_auth: false).
The public key fetch and cache are handled by the shared common/artemis_auth.
"""
import os
from typing import Optional

from fastapi import Header, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel

from common.artemis_auth import fetch_artemis_public_key


class TokenData(BaseModel):
    user_id: str
    email: str = ""


def require_token(authorization: Optional[str] = Header(None)) -> TokenData:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    raw = authorization.split(" ", 1)[1]
    try:
        unverified = jwt.get_unverified_claims(raw)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if unverified.get("iss") == "artemis-auth":
        pub_key = fetch_artemis_public_key()
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
