import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.database import get_connection, get_cursor, adapt_query, dict_from_row
from core.database import USE_SQLITE
from routers.auth import require_token
from schemas.models import SummaryCreate, SummaryUpdate, SummaryResponse

router = APIRouter(prefix="/summaries", tags=["summaries"])
logger = logging.getLogger(__name__)


def _row_to_summary(row: dict) -> dict:
    def _parse_list(val):
        if isinstance(val, str):
            return json.loads(val)
        return val or []

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "content_item_id": row["content_item_id"],
        "pillar_id": row.get("pillar_id"),
        "title": row["title"],
        "insights": _parse_list(row.get("insights", "[]")),
        "applications": _parse_list(row.get("applications", "[]")),
        "behavior_change": row.get("behavior_change"),
        "created_at": row["created_at"],
        "updated_at": row.get("updated_at"),
    }


@router.get("", response_model=List[SummaryResponse])
async def list_summaries(
    pillar_id: Optional[str] = None,
    content_item_id: Optional[str] = None,
    token: dict = Depends(require_token),
):
    user_id = token.get("user_id") or token.get("sub")
    conditions = ["user_id = %s"]
    params: list = [user_id]
    if pillar_id:
        conditions.append("pillar_id = %s")
        params.append(pillar_id)
    if content_item_id:
        conditions.append("content_item_id = %s")
        params.append(content_item_id)
    where = " AND ".join(conditions)
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(f"SELECT * FROM summaries WHERE {where} ORDER BY created_at DESC", USE_SQLITE),
            params,
        )
        rows = cur.fetchall()
    return [_row_to_summary(dict_from_row(r, USE_SQLITE)) for r in rows]


@router.post("", response_model=SummaryResponse, status_code=201)
async def create_summary(body: SummaryCreate, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    summary_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "INSERT INTO summaries "
                "(id, user_id, content_item_id, pillar_id, title, insights, applications, behavior_change, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                USE_SQLITE,
            ),
            (
                summary_id, user_id, body.content_item_id, body.pillar_id,
                body.title, json.dumps(body.insights), json.dumps(body.applications),
                body.behavior_change, now,
            ),
        )
        conn.commit()
    return {
        "id": summary_id, "user_id": user_id, "content_item_id": body.content_item_id,
        "pillar_id": body.pillar_id, "title": body.title, "insights": body.insights,
        "applications": body.applications, "behavior_change": body.behavior_change,
        "created_at": now, "updated_at": None,
    }


@router.get("/{summary_id}", response_model=SummaryResponse)
async def get_summary(summary_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("SELECT * FROM summaries WHERE id = %s AND user_id = %s", USE_SQLITE),
            (summary_id, user_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Summary not found")
    return _row_to_summary(dict_from_row(row, USE_SQLITE))


@router.patch("/{summary_id}", response_model=SummaryResponse)
async def update_summary(summary_id: str, body: SummaryUpdate, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "insights" in updates:
        updates["insights"] = json.dumps(updates["insights"])
    if "applications" in updates:
        updates["applications"] = json.dumps(updates["applications"])
    now = datetime.now(timezone.utc).isoformat()
    updates["updated_at"] = now
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [summary_id, user_id]
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(f"UPDATE summaries SET {set_clause} WHERE id = %s AND user_id = %s", USE_SQLITE),
            values,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Summary not found")
        cur.execute(adapt_query("SELECT * FROM summaries WHERE id = %s", USE_SQLITE), (summary_id,))
        row = cur.fetchone()
        conn.commit()
    return _row_to_summary(dict_from_row(row, USE_SQLITE))


@router.delete("/{summary_id}", status_code=204)
async def delete_summary(summary_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("DELETE FROM summaries WHERE id = %s AND user_id = %s", USE_SQLITE),
            (summary_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Summary not found")
        conn.commit()
