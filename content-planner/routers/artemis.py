"""Artemis Module Contract endpoints for Content Planner.

Accepts both standalone content-planner tokens AND Artemis platform tokens
(iss == "artemis-auth") via the shared dual-token auth in common/.
"""
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
MODULE_ID = "content-planner"

MANIFEST = {
    "module": {
        "id": MODULE_ID,
        "name": "Content Planner",
        "version": MODULE_VERSION,
        "contract_version": "1.0",
        "description": "Audio-first content consumption planning and tracking",
        "icon": "headphones",
        "color": "#ec4899",
        "standalone_url": "https://rummel-tech.github.io/content-planner/",
        "api_base": "https://api.rummeltech.com/content-planner",
    },
    "capabilities": {
        "auth": {"accepts_artemis_token": True, "standalone_auth": True},
        "dashboard_widgets": [
            {
                "id": "queue-summary",
                "name": "Queue Summary",
                "description": "Shows current queue status and next item",
                "size": "medium",
                "data_endpoint": "/artemis/widgets/queue-summary",
                "refresh_seconds": 300,
            },
            {
                "id": "inbox-count",
                "name": "Inbox Count",
                "description": "Number of unreviewed items in inbox",
                "size": "small",
                "data_endpoint": "/artemis/widgets/inbox-count",
                "refresh_seconds": 300,
            },
            {
                "id": "weekly-listening",
                "name": "Weekly Listening",
                "description": "Total listening time this week",
                "size": "small",
                "data_endpoint": "/artemis/widgets/weekly-listening",
                "refresh_seconds": 3600,
            },
            {
                "id": "pillar-progress",
                "name": "Pillar Progress",
                "description": "Content consumption by learning pillar",
                "size": "large",
                "data_endpoint": "/artemis/widgets/pillar-progress",
                "refresh_seconds": 3600,
            },
        ],
        "agent_tools": [
            {
                "id": "suggest-queue",
                "description": "AI-powered suggestions for what to add to your queue",
                "endpoint": "/artemis/agent/suggest-queue",
                "method": "POST",
                "parameters": {
                    "context": {
                        "type": "string",
                        "description": "Listening context: commute, workout, idle, or evening",
                        "required": False,
                    },
                    "duration_minutes": {
                        "type": "number",
                        "description": "Target duration in minutes",
                        "required": False,
                    },
                },
            },
        ],
        "provides_data": [
            {
                "id": "queue-stats",
                "name": "Queue Statistics",
                "description": "Current queue statistics",
                "endpoint": "/artemis/data/queue-stats",
            },
            {
                "id": "listening-summary",
                "name": "Listening Summary",
                "description": "Listening activity summary",
                "endpoint": "/artemis/data/listening-summary",
            },
        ],
        "consumes_data": [],
    },
}


@router.get("/manifest")
async def get_manifest() -> dict:
    """Return module manifest for Artemis platform discovery. No auth required."""
    return MANIFEST


@router.get("/widgets/{widget_id}")
async def get_widget(widget_id: str, token: TokenData = Depends(require_token)) -> dict:
    """Return widget data for Artemis platform rendering."""
    user_id = token.user_id

    if widget_id == "queue-summary":
        with get_connection() as conn:
            cur = get_cursor(conn)
            cur.execute(
                adapt_query(
                    "SELECT COUNT(*) as cnt, SUM(duration_ms) as total_ms FROM content_items "
                    "WHERE user_id = %s AND status = 'queued'",
                    USE_SQLITE,
                ),
                (user_id,),
            )
            row = dict_from_row(cur.fetchone(), USE_SQLITE)
            cur.execute(
                adapt_query(
                    "SELECT title FROM content_items WHERE user_id = %s AND status = 'queued' "
                    "ORDER BY queue_position LIMIT 1",
                    USE_SQLITE,
                ),
                (user_id,),
            )
            next_row = cur.fetchone()
        return {
            "widget_id": widget_id,
            "data": {
                "queue_count": row.get("cnt", 0),
                "total_duration_ms": row.get("total_ms") or 0,
                "next_item_title": dict_from_row(next_row, USE_SQLITE).get("title") if next_row else None,
            },
        }

    elif widget_id == "inbox-count":
        with get_connection() as conn:
            cur = get_cursor(conn)
            cur.execute(
                adapt_query(
                    "SELECT COUNT(*) as cnt FROM content_items WHERE user_id = %s AND status = 'inbox'",
                    USE_SQLITE,
                ),
                (user_id,),
            )
            row = dict_from_row(cur.fetchone(), USE_SQLITE)
        return {"widget_id": widget_id, "data": {"inbox_count": row.get("cnt", 0)}}

    elif widget_id == "weekly-listening":
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        with get_connection() as conn:
            cur = get_cursor(conn)
            cur.execute(
                adapt_query(
                    "SELECT SUM(listened_duration_ms) as total FROM sessions "
                    "WHERE user_id = %s AND started_at >= %s",
                    USE_SQLITE,
                ),
                (user_id, week_ago),
            )
            row = dict_from_row(cur.fetchone(), USE_SQLITE)
        return {
            "widget_id": widget_id,
            "data": {"weekly_listening_ms": row.get("total") or 0},
        }

    elif widget_id == "pillar-progress":
        with get_connection() as conn:
            cur = get_cursor(conn)
            cur.execute(
                adapt_query(
                    "SELECT pillar_id, COUNT(*) as cnt FROM content_items "
                    "WHERE user_id = %s AND status = 'completed' GROUP BY pillar_id",
                    USE_SQLITE,
                ),
                (user_id,),
            )
            rows = [dict_from_row(r, USE_SQLITE) for r in cur.fetchall()]
        return {
            "widget_id": widget_id,
            "data": {"by_pillar": {r["pillar_id"] or "none": r["cnt"] for r in rows}},
        }

    raise HTTPException(status_code=404, detail=f"Widget '{widget_id}' not found")


@router.post("/agent/{tool_id}")
async def run_agent(tool_id: str, body: dict, token: TokenData = Depends(require_token)) -> dict:
    """Execute an Artemis agent tool."""
    user_id = token.user_id

    if tool_id == "suggest-queue":
        context = body.get("context", "idle")
        duration_minutes = body.get("duration_minutes", 30)
        mode_map = {"commute": "tactical", "workout": "recovery", "idle": "deep", "evening": "deep"}
        preferred_mode = mode_map.get(context, "tactical")
        target_ms = duration_minutes * 60 * 1000

        with get_connection() as conn:
            cur = get_cursor(conn)
            cur.execute(
                adapt_query(
                    "SELECT id, title, duration_ms, mode, pillar_id FROM content_items "
                    "WHERE user_id = %s AND status = 'inbox' AND mode = %s "
                    "ORDER BY created_at LIMIT 5",
                    USE_SQLITE,
                ),
                (user_id, preferred_mode),
            )
            suggestions = [dict_from_row(r, USE_SQLITE) for r in cur.fetchall()]

        return {
            "tool_id": tool_id,
            "result": {
                "suggestions": suggestions,
                "context": context,
                "target_duration_ms": target_ms,
            },
        }

    raise HTTPException(status_code=404, detail=f"Agent tool '{tool_id}' not found")


@router.get("/data/{data_id}")
async def get_data(data_id: str, token: TokenData = Depends(require_token)) -> dict:
    """Return structured data for Artemis platform consumption."""
    user_id = token.user_id

    if data_id == "queue-stats":
        with get_connection() as conn:
            cur = get_cursor(conn)
            cur.execute(
                adapt_query(
                    "SELECT status, COUNT(*) as cnt FROM content_items "
                    "WHERE user_id = %s GROUP BY status",
                    USE_SQLITE,
                ),
                (user_id,),
            )
            by_status = {}
            for r in cur.fetchall():
                row = dict_from_row(r, USE_SQLITE)
                by_status[row["status"]] = row["cnt"]
        return {"data_id": data_id, "data": {"by_status": by_status}}

    elif data_id == "listening-summary":
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        with get_connection() as conn:
            cur = get_cursor(conn)
            cur.execute(
                adapt_query(
                    "SELECT SUM(listened_duration_ms) as today_ms FROM sessions "
                    "WHERE user_id = %s AND started_at >= %s",
                    USE_SQLITE,
                ),
                (user_id, today_start),
            )
            today_row = dict_from_row(cur.fetchone(), USE_SQLITE)
            cur.execute(
                adapt_query(
                    "SELECT SUM(listened_duration_ms) as week_ms FROM sessions "
                    "WHERE user_id = %s AND started_at >= %s",
                    USE_SQLITE,
                ),
                (user_id, week_ago),
            )
            week_row = dict_from_row(cur.fetchone(), USE_SQLITE)
        return {
            "data_id": data_id,
            "data": {
                "today_ms": today_row.get("today_ms") or 0,
                "week_ms": week_row.get("week_ms") or 0,
            },
        }

    raise HTTPException(status_code=404, detail=f"Data endpoint '{data_id}' not found")
