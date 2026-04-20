"""Artemis Module Contract endpoints for Trip Planner."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.database import get_connection, get_cursor, adapt_query, dict_from_row
from common.artemis_auth import create_artemis_token_dependency
from core.database import USE_SQLITE
from routers.auth import require_token as _standalone_require_token, decode_token, TokenData

router = APIRouter(prefix="/artemis", tags=["artemis"])
logger = logging.getLogger(__name__)

require_token = create_artemis_token_dependency(
    standalone_decoder=decode_token,
    token_data_class=TokenData,
)

MODULE_VERSION = "0.1.0"
MODULE_ID = "trip-planner"

MANIFEST = {
    "module": {
        "id": MODULE_ID,
        "name": "Trip Planner",
        "version": MODULE_VERSION,
        "contract_version": "1.0",
        "description": "Plan trips with itineraries, packing lists, and budget tracking",
        "icon": "flight",
        "color": "#0ea5e9",
        "standalone_url": "https://rummel-tech.github.io/trip-planner/",
        "api_base": "https://api.rummeltech.com/trip-planner",
    },
    "capabilities": {
        "auth": {"accepts_artemis_token": True, "standalone_auth": True},
        "dashboard_widgets": [
            {
                "id": "upcoming-trip",
                "name": "Upcoming Trip",
                "description": "Next upcoming trip with countdown and quick stats",
                "size": "medium",
                "data_endpoint": "/artemis/widgets/upcoming-trip",
                "refresh_seconds": 3600,
            },
            {
                "id": "active-trip",
                "name": "Active Trip",
                "description": "Today's itinerary for the current trip",
                "size": "large",
                "data_endpoint": "/artemis/widgets/active-trip",
                "refresh_seconds": 1800,
            },
        ],
    },
}


@router.get("/manifest")
async def get_manifest():
    return MANIFEST


@router.get("/widgets/upcoming-trip")
async def widget_upcoming_trip(token: TokenData = Depends(require_token)):
    today = datetime.now(timezone.utc).date().isoformat()
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "SELECT * FROM trips WHERE user_id = %s AND start_date >= %s"
                " AND status = 'planning' ORDER BY start_date LIMIT 1",
                USE_SQLITE,
            ),
            (token.user_id, today),
        )
        row = cur.fetchone()
        if not row:
            return {"has_trip": False}

        trip = dict_from_row(row, USE_SQLITE)
        days_until = 0
        if trip.get("start_date"):
            try:
                from datetime import date
                days_until = (date.fromisoformat(trip["start_date"]) - date.fromisoformat(today)).days
            except ValueError:
                pass

        cur.execute(
            adapt_query(
                "SELECT COUNT(*) AS cnt, SUM(packed) AS packed_cnt FROM packing_items WHERE trip_id = %s",
                USE_SQLITE,
            ),
            (trip["id"],),
        )
        pack_row = dict_from_row(cur.fetchone(), USE_SQLITE)

        return {
            "has_trip": True,
            "name": trip["name"],
            "destination": trip["destination"],
            "trip_type": trip["trip_type"],
            "start_date": trip["start_date"],
            "end_date": trip["end_date"],
            "days_until": days_until,
            "packing_total": pack_row.get("cnt", 0) or 0,
            "packing_packed": pack_row.get("packed_cnt", 0) or 0,
        }


@router.get("/widgets/active-trip")
async def widget_active_trip(token: TokenData = Depends(require_token)):
    today = datetime.now(timezone.utc).date().isoformat()
    with get_connection() as conn:
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "SELECT * FROM trips WHERE user_id = %s AND start_date <= %s AND end_date >= %s"
                " AND status IN ('planning','active') ORDER BY start_date LIMIT 1",
                USE_SQLITE,
            ),
            (token.user_id, today, today),
        )
        row = cur.fetchone()
        if not row:
            return {"has_active_trip": False}

        trip = dict_from_row(row, USE_SQLITE)
        cur.execute(
            adapt_query(
                "SELECT * FROM itinerary_items WHERE trip_id = %s AND day_date = %s ORDER BY position, start_time",
                USE_SQLITE,
            ),
            (trip["id"], today),
        )
        items = [dict_from_row(r, USE_SQLITE) for r in cur.fetchall()]

        return {
            "has_active_trip": True,
            "trip_name": trip["name"],
            "destination": trip["destination"],
            "today_items": [
                {
                    "title": i["title"],
                    "category": i["category"],
                    "start_time": i.get("start_time"),
                    "location": i.get("location"),
                }
                for i in items
            ],
        }
