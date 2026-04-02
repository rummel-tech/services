import logging
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.database import get_connection, get_cursor, adapt_query, dict_from_row
from core.database import USE_SQLITE
from routers.auth import require_token
from schemas.models import SourceCreate, SourceUpdate, SourceResponse

router = APIRouter(prefix="/sources", tags=["sources"])
logger = logging.getLogger(__name__)


def _row_to_source(row: dict) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "url": row.get("url"),
        "type": row["type"],
        "trust_level": row["trust_level"],
        "blocked": bool(row["blocked"]),
        "created_at": row["created_at"],
    }


@router.get("", response_model=List[SourceResponse])
async def list_sources(token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("SELECT * FROM sources WHERE user_id = %s ORDER BY title", USE_SQLITE),
            (user_id,),
        )
        rows = cur.fetchall()
    return [_row_to_source(dict_from_row(r, USE_SQLITE)) for r in rows]


@router.post("", response_model=SourceResponse, status_code=201)
async def create_source(body: SourceCreate, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    source_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "INSERT INTO sources (id, user_id, title, url, type, trust_level, blocked, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                USE_SQLITE,
            ),
            (source_id, user_id, body.title, body.url, body.type, body.trust_level, int(body.blocked), now),
        )
        conn.commit()
    return {
        "id": source_id, "user_id": user_id, "title": body.title,
        "url": body.url, "type": body.type, "trust_level": body.trust_level,
        "blocked": body.blocked, "created_at": now,
    }


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(source_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("SELECT * FROM sources WHERE id = %s AND user_id = %s", USE_SQLITE),
            (source_id, user_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    return _row_to_source(dict_from_row(row, USE_SQLITE))


@router.patch("/{source_id}", response_model=SourceResponse)
async def update_source(source_id: str, body: SourceUpdate, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "blocked" in updates:
        updates["blocked"] = int(updates["blocked"])
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [source_id, user_id]
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(f"UPDATE sources SET {set_clause} WHERE id = %s AND user_id = %s", USE_SQLITE),
            values,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Source not found")
        cur.execute(adapt_query("SELECT * FROM sources WHERE id = %s", USE_SQLITE), (source_id,))
        row = cur.fetchone()
        conn.commit()
    return _row_to_source(dict_from_row(row, USE_SQLITE))


@router.delete("/{source_id}", status_code=204)
async def delete_source(source_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("DELETE FROM sources WHERE id = %s AND user_id = %s", USE_SQLITE),
            (source_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Source not found")
        conn.commit()
