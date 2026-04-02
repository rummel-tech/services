import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.database import get_connection, get_cursor, adapt_query, dict_from_row
from core.database import USE_SQLITE
from routers.auth import require_token
from schemas.models import SessionCreate, SessionEnd, SessionResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = logging.getLogger(__name__)


def _row_to_session(row: dict) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "started_at": row["started_at"],
        "ended_at": row.get("ended_at"),
        "context": row["context"],
        "mode": row["mode"],
        "content_item_id": row.get("content_item_id"),
        "outcome": row.get("outcome"),
        "listened_duration_ms": row.get("listened_duration_ms", 0),
    }


@router.get("", response_model=List[SessionResponse])
async def list_sessions(
    context: Optional[str] = None,
    token: dict = Depends(require_token),
):
    user_id = token.get("user_id") or token.get("sub")
    conditions = ["user_id = %s"]
    params: list = [user_id]
    if context:
        conditions.append("context = %s")
        params.append(context)
    where = " AND ".join(conditions)
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(f"SELECT * FROM sessions WHERE {where} ORDER BY started_at DESC", USE_SQLITE),
            params,
        )
        rows = cur.fetchall()
    return [_row_to_session(dict_from_row(r, USE_SQLITE)) for r in rows]


@router.post("", response_model=SessionResponse, status_code=201)
async def start_session(body: SessionCreate, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "INSERT INTO sessions (id, user_id, started_at, context, mode, content_item_id, listened_duration_ms) "
                "VALUES (%s, %s, %s, %s, %s, %s, 0)",
                USE_SQLITE,
            ),
            (session_id, user_id, now, body.context, body.mode, body.content_item_id),
        )
        conn.commit()
    return {
        "id": session_id, "user_id": user_id, "started_at": now, "ended_at": None,
        "context": body.context, "mode": body.mode, "content_item_id": body.content_item_id,
        "outcome": None, "listened_duration_ms": 0,
    }


@router.get("/active", response_model=Optional[SessionResponse])
async def get_active_session(token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "SELECT * FROM sessions WHERE user_id = %s AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
                USE_SQLITE,
            ),
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return _row_to_session(dict_from_row(row, USE_SQLITE))


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("SELECT * FROM sessions WHERE id = %s AND user_id = %s", USE_SQLITE),
            (session_id, user_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return _row_to_session(dict_from_row(row, USE_SQLITE))


@router.post("/{session_id}/end", response_model=SessionResponse)
async def end_session(session_id: str, body: SessionEnd, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "UPDATE sessions SET ended_at = %s, outcome = %s, listened_duration_ms = %s "
                "WHERE id = %s AND user_id = %s",
                USE_SQLITE,
            ),
            (now, body.outcome, body.listened_duration_ms, session_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Session not found")
        cur.execute(adapt_query("SELECT * FROM sessions WHERE id = %s", USE_SQLITE), (session_id,))
        row = cur.fetchone()
        conn.commit()
    return _row_to_session(dict_from_row(row, USE_SQLITE))


@router.patch("/{session_id}/progress", response_model=SessionResponse)
async def update_progress(
    session_id: str,
    listened_duration_ms: int = Query(...),
    token: dict = Depends(require_token),
):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "UPDATE sessions SET listened_duration_ms = %s WHERE id = %s AND user_id = %s",
                USE_SQLITE,
            ),
            (listened_duration_ms, session_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Session not found")
        cur.execute(adapt_query("SELECT * FROM sessions WHERE id = %s", USE_SQLITE), (session_id,))
        row = cur.fetchone()
        conn.commit()
    return _row_to_session(dict_from_row(row, USE_SQLITE))
