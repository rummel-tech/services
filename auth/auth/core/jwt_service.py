"""RSA JWT service for Artemis platform tokens.

Signs tokens with a private RSA key. Modules verify using the public key
fetched from GET /auth/public-key — no shared secret needed.
"""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import JWTError, jwt

from auth.core.settings import get_settings

ALGORITHM = "RS256"
ISSUER = "artemis-auth"


def _load_or_generate_keys() -> tuple[str, str]:
    """Load RSA keys from env/files, generating them if absent (dev only)."""
    settings = get_settings()

    if settings.private_key_pem and settings.public_key_pem:
        return settings.private_key_pem, settings.public_key_pem

    private_path = Path(settings.private_key_path)
    public_path = Path(settings.public_key_path)

    if private_path.exists() and public_path.exists():
        return private_path.read_text(), public_path.read_text()

    # Generate new RSA key pair (dev only)
    if settings.environment == "production":
        raise RuntimeError(
            "RSA keys not configured. Set PRIVATE_KEY_PEM and PUBLIC_KEY_PEM env vars."
        )

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_text(private_pem)
    public_path.write_text(public_pem)

    return private_pem, public_pem


# Module-level cache — loaded once at startup
_private_key_pem: Optional[str] = None
_public_key_pem: Optional[str] = None


def init_keys() -> None:
    global _private_key_pem, _public_key_pem
    _private_key_pem, _public_key_pem = _load_or_generate_keys()


def get_public_key_pem() -> str:
    if _public_key_pem is None:
        raise RuntimeError("Keys not initialised — call init_keys() at startup")
    return _public_key_pem


def create_access_token(
    user_id: str,
    email: str,
    name: str,
    modules: list[str],
    permissions: list[str],
    expires_delta: Optional[timedelta] = None,
) -> str:
    settings = get_settings()
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "iss": ISSUER,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
        "type": "access",
        "modules": modules,
        "permissions": permissions,
    }
    return jwt.encode(payload, _private_key_pem, algorithm=ALGORITHM)


def create_refresh_token(user_id: str, email: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iss": ISSUER,
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    return jwt.encode(payload, _private_key_pem, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate an Artemis token. Returns payload or None."""
    try:
        return jwt.decode(
            token,
            _public_key_pem,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
        )
    except JWTError:
        return None
