"""Artemis platform integration router for Meal Planner.

Implements the Artemis Module Contract v1.0:
  GET  /artemis/manifest
  GET  /artemis/widgets/{widget_id}
  POST /artemis/agent/{tool_id}
  GET  /artemis/data/{data_id}

Accepts Artemis platform tokens (iss == "artemis-auth") verified against
the public key from the auth service at ARTEMIS_AUTH_URL.
"""
import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from common.database import adapt_query, get_connection, get_cursor, get_database_url, is_sqlite

USE_SQLITE = is_sqlite(get_database_url())
router = APIRouter(prefix="/artemis", tags=["artemis"])

ARTEMIS_AUTH_URL = os.getenv("ARTEMIS_AUTH_URL", "http://localhost:8090")
_artemis_public_key: Optional[str] = None
_artemis_public_key_fetched_at: float = 0.0
_KEY_CACHE_TTL = 86400  # 24 hours


def _fetch_artemis_public_key() -> Optional[str]:
    global _artemis_public_key, _artemis_public_key_fetched_at
    now = time.time()
    if _artemis_public_key and (now - _artemis_public_key_fetched_at) < _KEY_CACHE_TTL:
        return _artemis_public_key
    try:
        r = httpx.get(f"{ARTEMIS_AUTH_URL}/auth/public-key", timeout=3.0)
        if r.status_code == 200:
            _artemis_public_key = r.json()["public_key"]
            _artemis_public_key_fetched_at = now
            return _artemis_public_key
    except Exception:
        pass
    return None


class _TokenData(BaseModel):
    user_id: str
    email: str = ""


def require_token(authorization: Optional[str] = Header(None)) -> _TokenData:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    raw = authorization.split(" ", 1)[1]
    try:
        unverified = jwt.get_unverified_claims(raw)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if unverified.get("iss") == "artemis-auth":
        pub_key = _fetch_artemis_public_key()
        if pub_key:
            try:
                payload = jwt.decode(raw, pub_key, algorithms=["RS256"], issuer="artemis-auth")
                return _TokenData(user_id=payload["sub"], email=payload.get("email", ""))
            except JWTError as e:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
        # Dev fallback: auth service not running — only permitted outside production
        if os.getenv("ENVIRONMENT", "development") != "production":
            return _TokenData(user_id=unverified.get("sub", "dev-user"), email=unverified.get("email", ""))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service unavailable")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported token issuer")


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

MANIFEST = {
    "module": {
        "id": "meal-planner",
        "name": "Meal Planner",
        "version": "1.0.0",
        "contract_version": "1.0",
        "description": "Nutrition tracking and meal planning",
        "icon": "restaurant",
        "color": "#f97316",
        "standalone_url": "https://rummel-tech.github.io/meal-planner/",
        "api_base": "https://api.rummeltech.com/meal-planner",
    },
    "capabilities": {
        "auth": {"accepts_artemis_token": True, "standalone_auth": False},
        "dashboard_widgets": [
            {
                "id": "todays_nutrition",
                "name": "Today's Nutrition",
                "description": "Calories and macros logged today",
                "size": "medium",
                "data_endpoint": "/artemis/widgets/todays_nutrition",
                "refresh_seconds": 300,
            },
            {
                "id": "weekly_calories",
                "name": "Weekly Calories",
                "description": "Calorie intake trend this week",
                "size": "small",
                "data_endpoint": "/artemis/widgets/weekly_calories",
                "refresh_seconds": 3600,
            },
        ],
        "quick_actions": [
            {
                "id": "log_meal",
                "label": "Log Meal",
                "icon": "add_circle",
                "endpoint": "/artemis/agent/log_meal",
                "method": "POST",
            },
        ],
        "provides_data": [
            {
                "id": "daily_calories",
                "name": "Daily Calories Consumed",
                "description": "Total calories consumed per day",
                "endpoint": "/artemis/data/daily_calories",
                "schema": {
                    "date": "string (ISO date)",
                    "calories": "number",
                    "protein_g": "number",
                    "carbs_g": "number",
                    "fat_g": "number",
                },
                "requires_permission": "nutrition.calories.read",
            },
        ],
        "agent_tools": [
            {
                "id": "get_todays_meals",
                "description": "Get all meals logged today with nutrition totals",
                "endpoint": "/artemis/agent/get_todays_meals",
                "method": "GET",
                "parameters": {
                    "date": {"type": "string", "description": "ISO date, defaults to today", "required": False},
                },
            },
            {
                "id": "log_meal",
                "description": "Log a meal with nutrition information",
                "endpoint": "/artemis/agent/log_meal",
                "method": "POST",
                "parameters": {
                    "name": {"type": "string", "description": "Meal name", "required": True},
                    "meal_type": {"type": "string", "description": "breakfast, lunch, dinner, or snack", "required": True},
                    "calories": {"type": "number", "required": False},
                    "protein_g": {"type": "number", "required": False},
                    "carbs_g": {"type": "number", "required": False},
                    "fat_g": {"type": "number", "required": False},
                    "notes": {"type": "string", "required": False},
                },
            },
            {
                "id": "get_weekly_nutrition",
                "description": "Get nutrition summary for the current or specified week",
                "endpoint": "/artemis/agent/get_weekly_nutrition",
                "method": "GET",
                "parameters": {
                    "week_start": {"type": "string", "description": "ISO date of week start", "required": False},
                },
            },
        ],
    },
}


@router.get("/manifest")
def get_manifest() -> dict:
    return MANIFEST


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(sql: str, params: tuple) -> list[dict]:
    with get_connection() as conn:
        cur = get_cursor(conn, dict_cursor=not USE_SQLITE)
        if USE_SQLITE:
            sql = sql.replace("%s", "?")
        cur.execute(sql, params)
        rows = cur.fetchall()
        if USE_SQLITE:
            return [dict(zip([d[0] for d in cur.description], row)) for row in rows]
        return [dict(row) for row in rows]


def _day_totals(user_id: str, target_date: str) -> dict:
    rows = _q("SELECT calories, protein_g, carbs_g, fat_g, name, meal_type FROM meals WHERE user_id = %s AND date = %s", (user_id, target_date))
    meals = []
    total_cal = total_protein = total_carbs = total_fat = 0
    for row in rows:
        total_cal += row.get("calories") or 0
        total_protein += row.get("protein_g") or 0
        total_carbs += row.get("carbs_g") or 0
        total_fat += row.get("fat_g") or 0
        meals.append({"name": row.get("name"), "meal_type": row.get("meal_type"), "calories": row.get("calories") or 0})
    return {
        "meals": meals,
        "total_calories": total_cal,
        "total_protein_g": total_protein,
        "total_carbs_g": total_carbs,
        "total_fat_g": total_fat,
    }


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

@router.get("/widgets/{widget_id}")
def get_widget(widget_id: str, token: _TokenData = Depends(require_token)) -> dict:
    now = datetime.now(timezone.utc).isoformat() + "Z"
    user_id = token.user_id

    if widget_id == "todays_nutrition":
        today = str(date.today())
        data = _day_totals(user_id, today)
        return {
            "widget_id": "todays_nutrition",
            "data": {
                "date": today,
                "total_calories": data["total_calories"],
                "total_protein_g": data["total_protein_g"],
                "total_carbs_g": data["total_carbs_g"],
                "total_fat_g": data["total_fat_g"],
                "meal_count": len(data["meals"]),
            },
            "last_updated": now,
        }

    if widget_id == "weekly_calories":
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        days = []
        total = 0
        for i in range(7):
            d = str(week_start + timedelta(days=i))
            cals = _day_totals(user_id, d)["total_calories"]
            days.append({"date": d, "calories": cals})
            total += cals
        return {
            "widget_id": "weekly_calories",
            "data": {
                "week_start": str(week_start),
                "days": days,
                "average_calories": round(total / 7),
            },
            "last_updated": now,
        }

    raise HTTPException(status_code=404, detail=f"Unknown widget: {widget_id}")


# ---------------------------------------------------------------------------
# Agent tools
# ---------------------------------------------------------------------------

@router.get("/agent/get_todays_meals")
@router.post("/agent/get_todays_meals")
def agent_get_todays_meals(
    date: Optional[str] = None,
    body: Optional[dict] = None,
    token: _TokenData = Depends(require_token),
) -> dict:
    target_date = date or (body or {}).get("date") or str(datetime.today().date())
    data = _day_totals(token.user_id, target_date)
    return {"success": True, "result": {"date": target_date, **data}}


@router.post("/agent/log_meal")
def agent_log_meal(body: dict, token: _TokenData = Depends(require_token)) -> dict:
    name = body.get("name")
    meal_type = body.get("meal_type")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not meal_type:
        raise HTTPException(status_code=400, detail="meal_type is required")

    meal_id = str(uuid.uuid4())
    target_date = body.get("date") or str(date.today())

    with get_connection() as conn:
        cur = get_cursor(conn, dict_cursor=not USE_SQLITE)
        sql = """INSERT INTO meals (id, user_id, name, meal_type, date, calories, protein_g, carbs_g, fat_g, notes)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""" if USE_SQLITE else \
              """INSERT INTO meals (id, user_id, name, meal_type, date, calories, protein_g, carbs_g, fat_g, notes)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        cur.execute(sql, (
            meal_id, token.user_id, name, meal_type, target_date,
            body.get("calories"), body.get("protein_g"), body.get("carbs_g"),
            body.get("fat_g"), body.get("notes"),
        ))
        conn.commit()

    return {
        "success": True,
        "result": {"meal_id": meal_id, "name": name, "meal_type": meal_type, "date": target_date},
        "message": f"Logged {meal_type}: {name}",
    }


@router.get("/agent/get_weekly_nutrition")
@router.post("/agent/get_weekly_nutrition")
def agent_get_weekly_nutrition(
    week_start: Optional[str] = None,
    body: Optional[dict] = None,
    token: _TokenData = Depends(require_token),
) -> dict:
    ws_str = week_start or (body or {}).get("week_start")
    if ws_str:
        ws = date.fromisoformat(ws_str)
    else:
        today = date.today()
        ws = today - timedelta(days=today.weekday())

    days = []
    totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    for i in range(7):
        d = str(ws + timedelta(days=i))
        data = _day_totals(token.user_id, d)
        days.append({"date": d, "calories": data["total_calories"], "protein_g": data["total_protein_g"]})
        totals["calories"] += data["total_calories"]
        totals["protein_g"] += data["total_protein_g"]
        totals["carbs_g"] += data["total_carbs_g"]
        totals["fat_g"] += data["total_fat_g"]

    return {
        "success": True,
        "result": {
            "week_start": str(ws),
            "week_end": str(ws + timedelta(days=6)),
            "days": days,
            "totals": totals,
            "averages": {k: round(v / 7) for k, v in totals.items()},
        },
    }


# ---------------------------------------------------------------------------
# Cross-module data
# ---------------------------------------------------------------------------

@router.get("/data/{data_id}")
def get_shared_data(
    data_id: str,
    date: Optional[str] = None,
    token: _TokenData = Depends(require_token),
) -> dict:
    target_date = date or str(datetime.today().date())

    if data_id == "daily_calories":
        data = _day_totals(token.user_id, target_date)
        return {
            "data_id": "daily_calories",
            "data": {
                "date": target_date,
                "calories": data["total_calories"],
                "protein_g": data["total_protein_g"],
                "carbs_g": data["total_carbs_g"],
                "fat_g": data["total_fat_g"],
            },
        }

    raise HTTPException(status_code=404, detail=f"Unknown data_id: {data_id}")
