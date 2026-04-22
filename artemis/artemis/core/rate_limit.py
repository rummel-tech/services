"""Rate limiting for expensive AI endpoints.

Uses slowapi. Keys by authenticated user_id when available, falling back to IP.
Rate limits only enforced in production (ENVIRONMENT=production); dev/test get
a permissive 10000/minute ceiling to avoid interfering with tests.
"""
from fastapi import Request
from slowapi import Limiter

from artemis.core.settings import get_settings


def _rate_key(request: Request) -> str:
    """Key by user_id if a validated token is present; else fall back to IP."""
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    if request.client:
        return f"ip:{request.client.host}"
    return "anon"


_settings = get_settings()
_is_prod = _settings.environment == "production"

limiter = Limiter(
    key_func=_rate_key,
    default_limits=[] if _is_prod else ["10000/minute"],
)

# AI endpoint limits (per user, per minute / per hour)
AI_CHAT_LIMIT = "60/hour" if _is_prod else "10000/minute"
RESEARCH_LIMIT = "30/hour" if _is_prod else "10000/minute"
