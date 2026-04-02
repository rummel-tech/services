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
from schemas.models import PillarCreate, PillarUpdate, PillarResponse

router = APIRouter(prefix="/pillars", tags=["pillars"])
logger = logging.getLogger(__name__)


def _row_to_pillar(row: dict) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "color": row["color"],
        "priority_weight": row["priority_weight"],
        "is_quarterly_focus": bool(row["is_quarterly_focus"]),
        "created_at": row["created_at"],
    }


@router.get("", response_model=List[PillarResponse])
async def list_pillars(token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("SELECT * FROM pillars WHERE user_id = %s ORDER BY priority_weight DESC", USE_SQLITE),
            (user_id,),
        )
        rows = cur.fetchall()
    return [_row_to_pillar(dict_from_row(r, USE_SQLITE)) for r in rows]


@router.post("", response_model=PillarResponse, status_code=201)
async def create_pillar(body: PillarCreate, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    pillar_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "INSERT INTO pillars (id, user_id, name, color, priority_weight, is_quarterly_focus, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                USE_SQLITE,
            ),
            (pillar_id, user_id, body.name, body.color, body.priority_weight, int(body.is_quarterly_focus), now),
        )
        conn.commit()
    return {
        "id": pillar_id, "user_id": user_id, "name": body.name,
        "color": body.color, "priority_weight": body.priority_weight,
        "is_quarterly_focus": body.is_quarterly_focus, "created_at": now,
    }


@router.get("/{pillar_id}", response_model=PillarResponse)
async def get_pillar(pillar_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("SELECT * FROM pillars WHERE id = %s AND user_id = %s", USE_SQLITE),
            (pillar_id, user_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Pillar not found")
    return _row_to_pillar(dict_from_row(row, USE_SQLITE))


@router.patch("/{pillar_id}", response_model=PillarResponse)
async def update_pillar(pillar_id: str, body: PillarUpdate, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "is_quarterly_focus" in updates:
        updates["is_quarterly_focus"] = int(updates["is_quarterly_focus"])
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [pillar_id, user_id]
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(f"UPDATE pillars SET {set_clause} WHERE id = %s AND user_id = %s", USE_SQLITE),
            values,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Pillar not found")
        cur.execute(adapt_query("SELECT * FROM pillars WHERE id = %s", USE_SQLITE), (pillar_id,))
        row = cur.fetchone()
        conn.commit()
    return _row_to_pillar(dict_from_row(row, USE_SQLITE))


@router.delete("/{pillar_id}", status_code=204)
async def delete_pillar(pillar_id: str, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("DELETE FROM pillars WHERE id = %s AND user_id = %s", USE_SQLITE),
            (pillar_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Pillar not found")
        conn.commit()
