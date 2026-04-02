import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.database import get_connection, get_cursor, adapt_query, dict_from_row
from core.database import USE_SQLITE
from routers.auth import require_token
from routers.content_items import _row_to_item
from schemas.models import QueueReorder, QueueStats, ContentItemResponse

router = APIRouter(prefix="/queue", tags=["queue"])
logger = logging.getLogger(__name__)


@router.get("", response_model=List[ContentItemResponse])
async def get_queue(token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "SELECT * FROM content_items WHERE user_id = %s AND status = 'queued' "
                "ORDER BY queue_position",
                USE_SQLITE,
            ),
            (user_id,),
        )
        rows = cur.fetchall()
    return [_row_to_item(dict_from_row(r, USE_SQLITE)) for r in rows]


@router.get("/stats", response_model=QueueStats)
async def queue_stats(token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("SELECT * FROM user_settings WHERE user_id = %s", USE_SQLITE),
            (user_id,),
        )
        settings_row = cur.fetchone()
        cur.execute(
            adapt_query(
                "SELECT pillar_id, mode, duration_ms FROM content_items "
                "WHERE user_id = %s AND status = 'queued'",
                USE_SQLITE,
            ),
            (user_id,),
        )
        items = [dict_from_row(r, USE_SQLITE) for r in cur.fetchall()]

    total_cap = 10
    if settings_row:
        s = dict_from_row(settings_row, USE_SQLITE)
        total_cap = s.get("queue_total_cap", 10)

    total = len(items)
    by_pillar: dict = {}
    by_mode: dict = {}
    total_duration_ms = 0

    for item in items:
        pid = item.get("pillar_id") or "none"
        by_pillar[pid] = by_pillar.get(pid, 0) + 1
        m = item.get("mode", "tactical")
        by_mode[m] = by_mode.get(m, 0) + 1
        total_duration_ms += item.get("duration_ms", 0)

    return {
        "total": total,
        "total_cap": total_cap,
        "total_fill_pct": (total / total_cap * 100) if total_cap else 0.0,
        "by_pillar": by_pillar,
        "by_mode": by_mode,
        "total_duration_ms": total_duration_ms,
    }


@router.post("/reorder", status_code=204)
async def reorder_queue(body: QueueReorder, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        for position, item_id in enumerate(body.item_ids):
            cur.execute(
                adapt_query(
                    "UPDATE content_items SET queue_position = %s "
                    "WHERE id = %s AND user_id = %s AND status = 'queued'",
                    USE_SQLITE,
                ),
                (position, item_id, user_id),
            )
        conn.commit()


@router.post("/{item_id}/enqueue", response_model=ContentItemResponse)
async def enqueue_item(item_id: str, token: dict = Depends(require_token)):
    """Move a content item to the queue."""
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "SELECT COUNT(*) as cnt FROM content_items WHERE user_id = %s AND status = 'queued'",
                USE_SQLITE,
            ),
            (user_id,),
        )
        result = dict_from_row(cur.fetchone(), USE_SQLITE)
        position = result.get("cnt", 0)
        cur.execute(
            adapt_query(
                "UPDATE content_items SET status = 'queued', queue_position = %s "
                "WHERE id = %s AND user_id = %s",
                USE_SQLITE,
            ),
            (position, item_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Content item not found")
        cur.execute(adapt_query("SELECT * FROM content_items WHERE id = %s", USE_SQLITE), (item_id,))
        row = cur.fetchone()
        conn.commit()
    return _row_to_item(dict_from_row(row, USE_SQLITE))


@router.post("/{item_id}/dequeue", response_model=ContentItemResponse)
async def dequeue_item(item_id: str, token: dict = Depends(require_token)):
    """Move a queued item back to inbox."""
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "UPDATE content_items SET status = 'inbox', queue_position = 0 "
                "WHERE id = %s AND user_id = %s",
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


@router.get("/next", response_model=ContentItemResponse)
async def next_in_queue(token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "SELECT * FROM content_items WHERE user_id = %s AND status = 'queued' "
                "ORDER BY queue_position LIMIT 1",
                USE_SQLITE,
            ),
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Queue is empty")
    return _row_to_item(dict_from_row(row, USE_SQLITE))
