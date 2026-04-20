"""Itinerary items — day-by-day activities for a trip."""
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.database import get_connection, get_cursor, adapt_query, dict_from_row
from core.database import USE_SQLITE
from routers.auth import require_token, TokenData
from schemas.models import (
    ItineraryItemCreate, ItineraryItemUpdate,
    ItineraryItemResponse, ItineraryDayResponse,
)

router = APIRouter(prefix="/trips", tags=["itinerary"])
logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"accommodation", "transport", "food", "activity", "other"}


def _assert_trip_owner(trip_id: str, user_id: str, conn):
    cur = get_cursor(conn)
    cur.execute(
        adapt_query("SELECT id FROM trips WHERE id = %s AND user_id = %s", USE_SQLITE),
        (trip_id, user_id),
    )
    if not cur.fetchone():
        raise HTTPException(404, "Trip not found")


@router.get("/{trip_id}/itinerary", response_model=List[ItineraryDayResponse])
async def get_itinerary(trip_id: str, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        _assert_trip_owner(trip_id, token.user_id, conn)
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "SELECT * FROM itinerary_items WHERE trip_id = %s ORDER BY day_date, position, start_time",
                USE_SQLITE,
            ),
            (trip_id,),
        )
        items = [dict_from_row(r, USE_SQLITE) for r in cur.fetchall()]

    # Group by date
    days: dict[str, list] = {}
    for item in items:
        d = item["day_date"]
        days.setdefault(d, []).append(
            ItineraryItemResponse(**item, packed=None)
            if False
            else ItineraryItemResponse(
                id=item["id"], trip_id=item["trip_id"], day_date=item["day_date"],
                title=item["title"], location=item.get("location"),
                start_time=item.get("start_time"), end_time=item.get("end_time"),
                category=item["category"], notes=item.get("notes"),
                cost_cents=item["cost_cents"], position=item["position"],
                created_at=item["created_at"],
            )
        )
    return [ItineraryDayResponse(date=d, items=items_list) for d, items_list in sorted(days.items())]


@router.post("/{trip_id}/itinerary", response_model=ItineraryItemResponse, status_code=201)
async def add_itinerary_item(
    trip_id: str,
    body: ItineraryItemCreate,
    token: TokenData = Depends(require_token),
):
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"category must be one of {sorted(VALID_CATEGORIES)}")

    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        _assert_trip_owner(trip_id, token.user_id, conn)
        cur = get_cursor(conn)

        # Position = count of existing items for that day
        cur.execute(
            adapt_query(
                "SELECT COUNT(*) AS cnt FROM itinerary_items WHERE trip_id = %s AND day_date = %s",
                USE_SQLITE,
            ),
            (trip_id, body.day_date),
        )
        position = dict_from_row(cur.fetchone(), USE_SQLITE).get("cnt", 0) or 0

        cur.execute(
            adapt_query(
                """INSERT INTO itinerary_items
                   (id, trip_id, day_date, title, location, start_time, end_time,
                    category, notes, cost_cents, position, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING *""",
                USE_SQLITE,
            ),
            (
                item_id, trip_id, body.day_date, body.title, body.location,
                body.start_time, body.end_time, body.category, body.notes,
                body.cost_cents, position, now,
            ),
        )
        if USE_SQLITE:
            cur.execute(
                adapt_query("SELECT * FROM itinerary_items WHERE id = %s", USE_SQLITE), (item_id,)
            )
        row = dict_from_row(cur.fetchone(), USE_SQLITE)
        conn.commit()

    return ItineraryItemResponse(**row)


@router.patch("/{trip_id}/itinerary/{item_id}", response_model=ItineraryItemResponse)
async def update_itinerary_item(
    trip_id: str,
    item_id: str,
    body: ItineraryItemUpdate,
    token: TokenData = Depends(require_token),
):
    if body.category and body.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"category must be one of {sorted(VALID_CATEGORIES)}")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [item_id, trip_id]

    with get_connection() as conn:
        _assert_trip_owner(trip_id, token.user_id, conn)
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                f"UPDATE itinerary_items SET {set_clause} WHERE id = %s AND trip_id = %s",
                USE_SQLITE,
            ),
            values,
        )
        conn.commit()
        cur.execute(
            adapt_query("SELECT * FROM itinerary_items WHERE id = %s", USE_SQLITE), (item_id,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Item not found")
        return ItineraryItemResponse(**dict_from_row(row, USE_SQLITE))


@router.delete("/{trip_id}/itinerary/{item_id}", status_code=204)
async def delete_itinerary_item(
    trip_id: str, item_id: str, token: TokenData = Depends(require_token)
):
    with get_connection() as conn:
        _assert_trip_owner(trip_id, token.user_id, conn)
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "DELETE FROM itinerary_items WHERE id = %s AND trip_id = %s", USE_SQLITE
            ),
            (item_id, trip_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Item not found")
        conn.commit()
