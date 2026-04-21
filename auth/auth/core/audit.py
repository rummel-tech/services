"""Audit logging for authentication events."""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import Request
from auth.core.database import get_db, get_cursor


def log_event(
    event: str,
    request: Optional[Request] = None,
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Write an audit log entry. Never raises — failures are silent to avoid blocking auth flows."""
    try:
        ip = None
        ua = None
        if request:
            ip = request.client.host if request.client else None
            ua = request.headers.get("user-agent", "")[:500]

        with get_db() as conn:
            cur = get_cursor(conn)
            cur.execute(
                """INSERT INTO audit_logs (id, user_id, event, ip_address, user_agent, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    user_id,
                    event,
                    ip,
                    ua,
                    json.dumps(metadata or {}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    except Exception:
        pass  # Audit log failures must never break auth
