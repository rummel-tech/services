"""Packing list — items to pack per trip, with category templates."""
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
from schemas.models import PackingItemCreate, PackingItemUpdate, PackingItemResponse

router = APIRouter(prefix="/trips", tags=["packing"])
logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"clothing", "toiletries", "documents", "electronics", "gear", "food", "general"}

# Default packing templates per trip type
PACKING_TEMPLATES: dict[str, list[dict]] = {
    "road_trip": [
        {"category": "documents", "name": "Driver's license", "quantity": 1},
        {"category": "documents", "name": "Vehicle registration", "quantity": 1},
        {"category": "documents", "name": "Insurance card", "quantity": 1},
        {"category": "gear", "name": "Phone car mount", "quantity": 1},
        {"category": "gear", "name": "Phone charger / car adapter", "quantity": 1},
        {"category": "gear", "name": "Paper maps / offline maps downloaded", "quantity": 1},
        {"category": "food", "name": "Snacks", "quantity": 1},
        {"category": "food", "name": "Water bottles", "quantity": 2},
        {"category": "gear", "name": "First aid kit", "quantity": 1},
        {"category": "clothing", "name": "Comfortable driving clothes", "quantity": 1},
    ],
    "camping": [
        {"category": "gear", "name": "Tent", "quantity": 1},
        {"category": "gear", "name": "Sleeping bag", "quantity": 1},
        {"category": "gear", "name": "Sleeping pad", "quantity": 1},
        {"category": "gear", "name": "Flashlight / headlamp", "quantity": 1},
        {"category": "gear", "name": "Bug spray", "quantity": 1},
        {"category": "gear", "name": "Sunscreen", "quantity": 1},
        {"category": "gear", "name": "Fire starter / matches", "quantity": 1},
        {"category": "food", "name": "Camp stove + fuel", "quantity": 1},
        {"category": "gear", "name": "Water filter / purification tablets", "quantity": 1},
        {"category": "clothing", "name": "Rain jacket", "quantity": 1},
        {"category": "clothing", "name": "Hiking boots", "quantity": 1},
        {"category": "clothing", "name": "Warm layers", "quantity": 2},
    ],
    "international": [
        {"category": "documents", "name": "Passport", "quantity": 1},
        {"category": "documents", "name": "Travel insurance documents", "quantity": 1},
        {"category": "documents", "name": "Visa / entry documents", "quantity": 1},
        {"category": "documents", "name": "Emergency contacts printed", "quantity": 1},
        {"category": "electronics", "name": "Universal travel adapter", "quantity": 1},
        {"category": "electronics", "name": "Phone + charger", "quantity": 1},
        {"category": "gear", "name": "Local currency / travel card", "quantity": 1},
        {"category": "toiletries", "name": "Prescription medications", "quantity": 1},
        {"category": "gear", "name": "Luggage locks", "quantity": 2},
    ],
    "business": [
        {"category": "documents", "name": "Business cards", "quantity": 1},
        {"category": "electronics", "name": "Laptop + charger", "quantity": 1},
        {"category": "electronics", "name": "Phone + charger", "quantity": 1},
        {"category": "electronics", "name": "Presentation clicker", "quantity": 1},
        {"category": "clothing", "name": "Dress clothes", "quantity": 2},
        {"category": "clothing", "name": "Dress shoes", "quantity": 1},
        {"category": "clothing", "name": "Smart casual clothes", "quantity": 2},
        {"category": "toiletries", "name": "Travel toiletries", "quantity": 1},
    ],
    "vacation": [
        {"category": "toiletries", "name": "Sunscreen", "quantity": 1},
        {"category": "clothing", "name": "Swimsuit", "quantity": 2},
        {"category": "clothing", "name": "Casual clothes", "quantity": 3},
        {"category": "clothing", "name": "Comfortable shoes", "quantity": 1},
        {"category": "electronics", "name": "Camera", "quantity": 1},
        {"category": "electronics", "name": "Phone + charger", "quantity": 1},
        {"category": "gear", "name": "Daypack", "quantity": 1},
        {"category": "toiletries", "name": "Travel toiletries kit", "quantity": 1},
    ],
}
# weekend and flight get the vacation template
PACKING_TEMPLATES["weekend"] = PACKING_TEMPLATES["vacation"]
PACKING_TEMPLATES["flight"] = PACKING_TEMPLATES["vacation"]


def _assert_trip_owner(trip_id: str, user_id: str, conn):
    cur = get_cursor(conn)
    cur.execute(
        adapt_query("SELECT id, trip_type FROM trips WHERE id = %s AND user_id = %s", USE_SQLITE),
        (trip_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Trip not found")
    return dict_from_row(row, USE_SQLITE)


@router.get("/{trip_id}/packing", response_model=List[PackingItemResponse])
async def get_packing_list(trip_id: str, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        _assert_trip_owner(trip_id, token.user_id, conn)
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "SELECT * FROM packing_items WHERE trip_id = %s ORDER BY category, name",
                USE_SQLITE,
            ),
            (trip_id,),
        )
        return [
            PackingItemResponse(**{**dict_from_row(r, USE_SQLITE), "packed": bool(dict_from_row(r, USE_SQLITE)["packed"])})
            for r in cur.fetchall()
        ]


@router.post("/{trip_id}/packing/seed", response_model=List[PackingItemResponse], status_code=201)
async def seed_packing_list(trip_id: str, token: TokenData = Depends(require_token)):
    """Populate a starter packing list based on the trip type."""
    with get_connection() as conn:
        trip = _assert_trip_owner(trip_id, token.user_id, conn)
        template = PACKING_TEMPLATES.get(trip["trip_type"], PACKING_TEMPLATES["vacation"])
        now = datetime.now(timezone.utc).isoformat()
        cur = get_cursor(conn)

        # Clear existing to avoid duplicates on re-seed
        cur.execute(
            adapt_query("DELETE FROM packing_items WHERE trip_id = %s", USE_SQLITE), (trip_id,)
        )

        created = []
        for tmpl in template:
            item_id = str(uuid.uuid4())
            cur.execute(
                adapt_query(
                    "INSERT INTO packing_items (id, trip_id, category, name, quantity, packed, added_at)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    USE_SQLITE,
                ),
                (item_id, trip_id, tmpl["category"], tmpl["name"], tmpl["quantity"], 0, now),
            )
            created.append(PackingItemResponse(
                id=item_id, trip_id=trip_id, category=tmpl["category"],
                name=tmpl["name"], quantity=tmpl["quantity"], packed=False, added_at=now,
            ))
        conn.commit()
        return created


@router.post("/{trip_id}/packing", response_model=PackingItemResponse, status_code=201)
async def add_packing_item(
    trip_id: str,
    body: PackingItemCreate,
    token: TokenData = Depends(require_token),
):
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        _assert_trip_owner(trip_id, token.user_id, conn)
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "INSERT INTO packing_items (id, trip_id, category, name, quantity, packed, added_at)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                USE_SQLITE,
            ),
            (item_id, trip_id, body.category, body.name, body.quantity, 0, now),
        )
        conn.commit()
    return PackingItemResponse(
        id=item_id, trip_id=trip_id, category=body.category,
        name=body.name, quantity=body.quantity, packed=False, added_at=now,
    )


@router.patch("/{trip_id}/packing/{item_id}", response_model=PackingItemResponse)
async def update_packing_item(
    trip_id: str,
    item_id: str,
    body: PackingItemUpdate,
    token: TokenData = Depends(require_token),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    if "packed" in updates:
        updates["packed"] = 1 if updates["packed"] else 0

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [item_id, trip_id]

    with get_connection() as conn:
        _assert_trip_owner(trip_id, token.user_id, conn)
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                f"UPDATE packing_items SET {set_clause} WHERE id = %s AND trip_id = %s",
                USE_SQLITE,
            ),
            values,
        )
        conn.commit()
        cur.execute(
            adapt_query("SELECT * FROM packing_items WHERE id = %s", USE_SQLITE), (item_id,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Item not found")
        d = dict_from_row(row, USE_SQLITE)
        return PackingItemResponse(**{**d, "packed": bool(d["packed"])})


@router.delete("/{trip_id}/packing/{item_id}", status_code=204)
async def delete_packing_item(
    trip_id: str, item_id: str, token: TokenData = Depends(require_token)
):
    with get_connection() as conn:
        _assert_trip_owner(trip_id, token.user_id, conn)
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "DELETE FROM packing_items WHERE id = %s AND trip_id = %s", USE_SQLITE
            ),
            (item_id, trip_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Item not found")
        conn.commit()
