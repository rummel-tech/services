"""Trip CRUD — create, list, get, update, delete trips."""
import logging
import uuid
from datetime import datetime, timezone, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.database import get_connection, get_cursor, adapt_query, dict_from_row
from core.database import USE_SQLITE
from routers.auth import require_token, TokenData
from schemas.models import TripCreate, TripUpdate, TripResponse

router = APIRouter(prefix="/trips", tags=["trips"])
logger = logging.getLogger(__name__)

VALID_TYPES = {"road_trip", "flight", "vacation", "business", "weekend", "camping", "international"}
VALID_STATUSES = {"planning", "active", "completed"}


def _build_trip_response(row: dict, conn) -> TripResponse:
    """Attach computed fields to a trip row."""
    cur = get_cursor(conn)

    # Total days
    total_days = 0
    if row.get("start_date") and row.get("end_date"):
        try:
            start = date.fromisoformat(row["start_date"])
            end = date.fromisoformat(row["end_date"])
            total_days = max(0, (end - start).days + 1)
        except ValueError:
            pass

    # Total spent
    cur.execute(
        adapt_query("SELECT COALESCE(SUM(amount_cents), 0) AS total FROM trip_expenses WHERE trip_id = %s", USE_SQLITE),
        (row["id"],),
    )
    spent = dict_from_row(cur.fetchone(), USE_SQLITE).get("total", 0) or 0

    budget = row.get("budget_cents", 0) or 0
    remaining = max(0, budget - spent)

    return TripResponse(
        **row,
        total_days=total_days,
        spent_cents=spent,
        remaining_cents=remaining,
    )


@router.get("", response_model=list[TripResponse])
async def list_trips(
    status: Optional[str] = Query(None),
    token: TokenData = Depends(require_token),
):
    sql = "SELECT * FROM trips WHERE user_id = %s"
    params: list = [token.user_id]
    if status:
        sql += " AND status = %s"
        params.append(status)
    sql += " ORDER BY COALESCE(start_date, created_at) DESC"

    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(adapt_query(sql, USE_SQLITE), params)
        rows = [dict_from_row(r, USE_SQLITE) for r in cur.fetchall()]
        return [_build_trip_response(r, conn) for r in rows]


@router.post("", response_model=TripResponse, status_code=201)
async def create_trip(
    body: TripCreate,
    token: TokenData = Depends(require_token),
):
    if body.trip_type not in VALID_TYPES:
        raise HTTPException(400, f"trip_type must be one of {sorted(VALID_TYPES)}")

    trip_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                """INSERT INTO trips
                   (id, user_id, name, destination, trip_type,
                    start_date, end_date, budget_cents, notes, status,
                    created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING *""",
                USE_SQLITE,
            ),
            (
                trip_id, token.user_id, body.name, body.destination,
                body.trip_type, body.start_date, body.end_date,
                body.budget_cents, body.notes, "planning", now, now,
            ),
        )
        if USE_SQLITE:
            cur.execute(adapt_query("SELECT * FROM trips WHERE id = %s", USE_SQLITE), (trip_id,))
        row = dict_from_row(cur.fetchone(), USE_SQLITE)
        conn.commit()
        return _build_trip_response(row, conn)


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(trip_id: str, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("SELECT * FROM trips WHERE id = %s AND user_id = %s", USE_SQLITE),
            (trip_id, token.user_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Trip not found")
        return _build_trip_response(dict_from_row(row, USE_SQLITE), conn)


@router.patch("/{trip_id}", response_model=TripResponse)
async def update_trip(
    trip_id: str,
    body: TripUpdate,
    token: TokenData = Depends(require_token),
):
    if body.trip_type and body.trip_type not in VALID_TYPES:
        raise HTTPException(400, f"trip_type must be one of {sorted(VALID_TYPES)}")
    if body.status and body.status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(VALID_STATUSES)}")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [trip_id, token.user_id]

    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(f"UPDATE trips SET {set_clause} WHERE id = %s AND user_id = %s", USE_SQLITE),
            values,
        )
        conn.commit()
        cur.execute(
            adapt_query("SELECT * FROM trips WHERE id = %s AND user_id = %s", USE_SQLITE),
            (trip_id, token.user_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Trip not found")
        return _build_trip_response(dict_from_row(row, USE_SQLITE), conn)


@router.delete("/{trip_id}", status_code=204)
async def delete_trip(trip_id: str, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query("DELETE FROM trips WHERE id = %s AND user_id = %s", USE_SQLITE),
            (trip_id, token.user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Trip not found")
        conn.commit()
