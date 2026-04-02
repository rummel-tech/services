import json
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
from schemas.models import ContentItemCreate, ContentItemUpdate, ContentItemResponse

router = APIRouter(prefix="/content", tags=["content"])
logger = logging.getLogger(__name__)


def _row_to_item(row: dict) -> dict:
    topics = row.get("topics", "[]")
    if isinstance(topics, str):
        topics = json.loads(topics)
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "source_id": row.get("source_id"),
        "title": row["title"],
        "url": row.get("url"),
        "type": row["type"],
        "duration_ms": row["duration_ms"],
        "published_at": row.get("published_at"),
        "topics": topics,
        "pillar_id": row.get("pillar_id"),
        "mode": row["mode"],
        "status": row["status"],
        "play_state": {
            "position_ms": row.get("play_position_ms", 0),
            "completed_at": row.get("play_completed_at"),
        },
        "feedback": {
            "skip_count": row.get("skip_count", 0),
            "redundant_flag": bool(row.get("redundant_flag", 0)),
            "last_skipped_at": row.get("last_skipped_at"),
        },
        "similarity_key": row.get("similarity_key"),
        "queue_position": row.get("queue_position", 0),
        "created_at": row["created_at"],
    }


@router.get("", response_model=List[ContentItemResponse])
async def list_content(
    status: Optional[str] = None,
    pillar_id: Optional[str] = None,
    mode: Optional[str] = None,
    token: dict = Depends(require_token),
):
    user_id = token.get("user_id") or token.get("sub")
    conditions = ["user_id = %s"]
    params: list = [user_id]
    if status:
        conditions.append("status = %s")
        params.append(status)
    if pillar_id:
        conditions.append("pillar_id = %s")
        params.append(pillar_id)
    if mode:
        conditions.append("mode = %s")
        params.append(mode)
    where = " AND ".join(conditions)
    sql = f"SELECT * FROM content_items WHERE {where} ORDER BY queue_position, created_at DESC"
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(adapt_query(sql, USE_SQLITE), params)
        rows = cur.fetchall()
    return [_row_to_item(dict_from_row(r, USE_SQLITE)) for r in rows]


@router.post("", response_model=ContentItemResponse, status_code=201)
async def create_content_item(body: ContentItemCreate, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    topics_json = json.dumps(body.topics)
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "INSERT INTO content_items "
                "(id, user_id, source_id, title, url, type, duration_ms, published_at, topics, "
                "pillar_id, mode, status, play_position_ms, skip_count, redundant_flag, "
                "queue_position, similarity_key, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, 0, 0, %s, %s)",
                USE_SQLITE,
            ),
            (
                item_id, user_id, body.source_id, body.title, body.url,
                body.type, body.duration_ms, body.published_at, topics_json,
                body.pillar_id, body.mode, body.status, body.similarity_key, now,
            ),
        )
        conn.commit()
    return _row_to_item({
        "id": item_id, "user_id": user_id, "source_id": body.source_id,
        "title": body.title, "url": body.url, "type": body.type,
        "duration_ms": body.duration_ms, "published_at": body.published_at,
        "topics": body.topics, "pillar_id": body.pillar_id, "mode": body.mode,
        "status": body.status, "play_position_ms": 0, "play_completed_at": None,
        "skip_count": 0, "redundant_flag": 0, "last_skipped_at": None,
        "similarity_key": body.similarity_key, "queue_position": 0, "created_at": now,
    })


@router.get("/{item_id}", response_model=ContentItemResponse)
async def get_content_item(item_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("SELECT * FROM content_items WHERE id = %s AND user_id = %s", USE_SQLITE),
            (item_id, user_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Content item not found")
    return _row_to_item(dict_from_row(row, USE_SQLITE))


@router.patch("/{item_id}", response_model=ContentItemResponse)
async def update_content_item(item_id: str, body: ContentItemUpdate, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "topics" in updates:
        updates["topics"] = json.dumps(updates["topics"])
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [item_id, user_id]
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                f"UPDATE content_items SET {set_clause} WHERE id = %s AND user_id = %s",
                USE_SQLITE,
            ),
            values,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Content item not found")
        cur.execute(adapt_query("SELECT * FROM content_items WHERE id = %s", USE_SQLITE), (item_id,))
        row = cur.fetchone()
        conn.commit()
    return _row_to_item(dict_from_row(row, USE_SQLITE))


@router.delete("/{item_id}", status_code=204)
async def delete_content_item(item_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("DELETE FROM content_items WHERE id = %s AND user_id = %s", USE_SQLITE),
            (item_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Content item not found")
        conn.commit()


@router.post("/{item_id}/play-position", response_model=ContentItemResponse)
async def update_play_position(
    item_id: str,
    position_ms: int = Query(...),
    token: dict = Depends(require_token),
):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "UPDATE content_items SET play_position_ms = %s WHERE id = %s AND user_id = %s",
                USE_SQLITE,
            ),
            (position_ms, item_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Content item not found")
        cur.execute(adapt_query("SELECT * FROM content_items WHERE id = %s", USE_SQLITE), (item_id,))
        row = cur.fetchone()
        conn.commit()
    return _row_to_item(dict_from_row(row, USE_SQLITE))


@router.post("/{item_id}/skip", response_model=ContentItemResponse)
async def record_skip(item_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "UPDATE content_items SET skip_count = skip_count + 1, last_skipped_at = %s "
                "WHERE id = %s AND user_id = %s",
                USE_SQLITE,
            ),
            (now, item_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Content item not found")
        cur.execute(adapt_query("SELECT * FROM content_items WHERE id = %s", USE_SQLITE), (item_id,))
        row = cur.fetchone()
        conn.commit()
    return _row_to_item(dict_from_row(row, USE_SQLITE))


@router.post("/{item_id}/flag-redundant", response_model=ContentItemResponse)
async def flag_redundant(item_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "UPDATE content_items SET redundant_flag = 1 WHERE id = %s AND user_id = %s",
                USE_SQLITE,
            ),
            (item_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Content item not found")
        cur.execute(adapt_query("SELECT * FROM content_items WHERE id = %s", USE_SQLITE), (item_id,))
        row = cur.fetchone()
        conn.commit()
    return _row_to_item(dict_from_row(row, USE_SQLITE))


@router.post("/{item_id}/complete", response_model=ContentItemResponse)
async def mark_completed(item_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "UPDATE content_items SET status = 'completed', play_completed_at = %s "
                "WHERE id = %s AND user_id = %s",
                USE_SQLITE,
            ),
            (now, item_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Content item not found")
        cur.execute(adapt_query("SELECT * FROM content_items WHERE id = %s", USE_SQLITE), (item_id,))
        row = cur.fetchone()
        conn.commit()
    return _row_to_item(dict_from_row(row, USE_SQLITE))
