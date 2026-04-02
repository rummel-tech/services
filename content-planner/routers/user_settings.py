import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.database import get_connection, get_cursor, adapt_query, dict_from_row
from core.database import USE_SQLITE
from routers.auth import require_token
from schemas.models import UserSettingsUpdate, UserSettingsResponse, QueueCapsUpdate, NotificationSettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger(__name__)

_DEFAULT_CONTEXT_MODE_MAP = {
    "commute": "tactical",
    "workout": "recovery",
    "idle": "deep",
    "evening": "deep",
}


def _row_to_settings(row: dict) -> dict:
    def _parse_list(val):
        if isinstance(val, str):
            return json.loads(val)
        return val or []

    def _parse_dict(val):
        if isinstance(val, str):
            return json.loads(val)
        return val or {}

    return {
        "user_id": row["user_id"],
        "pillar_ids": _parse_list(row.get("pillar_ids", "[]")),
        "trusted_source_ids": _parse_list(row.get("trusted_source_ids", "[]")),
        "blocked_source_ids": _parse_list(row.get("blocked_source_ids", "[]")),
        "context_mode_map": _parse_dict(row.get("context_mode_map", "{}")),
        "queue_caps": {
            "total_cap": row.get("queue_total_cap", 10),
            "per_pillar_cap": row.get("queue_per_pillar_cap", 5),
            "per_mode_cap": row.get("queue_per_mode_cap", 5),
        },
        "start_behavior": row.get("start_behavior", "auto"),
        "notifications": {
            "weekly_review_reminder": bool(row.get("notif_weekly_review", 1)),
            "queue_empty_alert": bool(row.get("notif_queue_empty", 1)),
            "inbox_overflow_alert": bool(row.get("notif_inbox_overflow", 0)),
            "inbox_overflow_threshold": row.get("notif_inbox_overflow_threshold", 20),
        },
        "quarterly_focus_pillar_id": row.get("quarterly_focus_pillar_id"),
        "updated_at": row["updated_at"],
    }


def _ensure_settings(conn, user_id: str) -> dict:
    """Return settings row, creating defaults if missing."""
    cur = get_cursor(conn)
    cur.execute(
        adapt_query("SELECT * FROM user_settings WHERE user_id = %s", USE_SQLITE),
        (user_id,),
    )
    row = cur.fetchone()
    if row:
        return dict_from_row(row, USE_SQLITE)

    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        adapt_query(
            "INSERT INTO user_settings (user_id, pillar_ids, trusted_source_ids, blocked_source_ids, "
            "context_mode_map, queue_total_cap, queue_per_pillar_cap, queue_per_mode_cap, "
            "start_behavior, notif_weekly_review, notif_queue_empty, notif_inbox_overflow, "
            "notif_inbox_overflow_threshold, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, 10, 5, 5, 'auto', 1, 1, 0, 20, %s)",
            USE_SQLITE,
        ),
        (
            user_id,
            "[]", "[]", "[]",
            json.dumps(_DEFAULT_CONTEXT_MODE_MAP),
            now,
        ),
    )
    conn.commit()
    cur.execute(
        adapt_query("SELECT * FROM user_settings WHERE user_id = %s", USE_SQLITE),
        (user_id,),
    )
    return dict_from_row(cur.fetchone(), USE_SQLITE)


@router.get("", response_model=UserSettingsResponse)
async def get_settings(token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    with get_connection() as conn:
        row = _ensure_settings(conn, user_id)
    return _row_to_settings(row)


@router.patch("", response_model=UserSettingsResponse)
async def update_settings(body: UserSettingsUpdate, token: dict = Depends(require_token)):
    user_id = token.get("user_id") or token.get("sub")
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        _ensure_settings(conn, user_id)

        updates: dict = {"updated_at": now}
        data = body.model_dump(exclude_none=True)

        if "pillar_ids" in data:
            updates["pillar_ids"] = json.dumps(data["pillar_ids"])
        if "trusted_source_ids" in data:
            updates["trusted_source_ids"] = json.dumps(data["trusted_source_ids"])
        if "blocked_source_ids" in data:
            updates["blocked_source_ids"] = json.dumps(data["blocked_source_ids"])
        if "context_mode_map" in data:
            updates["context_mode_map"] = json.dumps(data["context_mode_map"])
        if "start_behavior" in data:
            updates["start_behavior"] = data["start_behavior"]
        if "quarterly_focus_pillar_id" in data:
            updates["quarterly_focus_pillar_id"] = data["quarterly_focus_pillar_id"]
        if "queue_caps" in data:
            caps = data["queue_caps"]
            updates["queue_total_cap"] = caps.get("total_cap", 10)
            updates["queue_per_pillar_cap"] = caps.get("per_pillar_cap", 5)
            updates["queue_per_mode_cap"] = caps.get("per_mode_cap", 5)
        if "notifications" in data:
            n = data["notifications"]
            updates["notif_weekly_review"] = int(n.get("weekly_review_reminder", True))
            updates["notif_queue_empty"] = int(n.get("queue_empty_alert", True))
            updates["notif_inbox_overflow"] = int(n.get("inbox_overflow_alert", False))
            updates["notif_inbox_overflow_threshold"] = n.get("inbox_overflow_threshold", 20)

        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [user_id]

        cur = get_cursor(conn)
        cur.execute(
            adapt_query(f"UPDATE user_settings SET {set_clause} WHERE user_id = %s", USE_SQLITE),
            values,
        )
        cur.execute(adapt_query("SELECT * FROM user_settings WHERE user_id = %s", USE_SQLITE), (user_id,))
        row = dict_from_row(cur.fetchone(), USE_SQLITE)
        conn.commit()

    return _row_to_settings(row)
