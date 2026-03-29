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
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from common.database import get_connection, get_cursor, get_database_url, is_sqlite
from routers.auth import TokenData as _TokenData, require_token

WORKOUT_PLANNER_URL = os.getenv("WORKOUT_PLANNER_URL", "http://localhost:8000")

USE_SQLITE = is_sqlite(get_database_url())
router = APIRouter(prefix="/artemis", tags=["artemis"])


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
                "description": "Total calories consumed per day, with optional net calories if workout data available",
                "endpoint": "/artemis/data/daily_calories",
                "schema": {
                    "date": "string (ISO date)",
                    "calories": "number",
                    "protein_g": "number",
                    "carbs_g": "number",
                    "fat_g": "number",
                    "calories_burned": "number | null",
                    "net_calories": "number | null",
                },
                "requires_permission": "nutrition.calories.read",
            },
        ],
        "consumes_data": [
            {
                "module_id": "workout-planner",
                "data_id": "calories_burned",
                "description": "Calories burned from workouts, used to calculate net calories",
                "optional": True,
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
        "optional_endpoints": [
            {
                "path": "/artemis/summary",
                "description": "Natural language nutrition summary for AI briefings",
            },
            {
                "path": "/artemis/calendar",
                "description": "Upcoming calendar events for the next 14 days",
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


def _fetch_calories_burned(authorization: str, target_date: str) -> Optional[int]:
    """Best-effort fetch of calories burned from workout-planner. Returns None on any failure."""
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(
                f"{WORKOUT_PLANNER_URL}/artemis/data/calories_burned",
                params={"date": target_date},
                headers={"Authorization": authorization},
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                return data.get("calories")
    except Exception:
        pass
    return None


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
    authorization: Optional[str] = Header(None),
    token: _TokenData = Depends(require_token),
) -> dict:
    target_date = date or str(datetime.today().date())

    if data_id == "daily_calories":
        data = _day_totals(token.user_id, target_date)
        calories_burned = _fetch_calories_burned(authorization or "", target_date)
        net_calories = (data["total_calories"] - calories_burned) if calories_burned is not None else None
        return {
            "data_id": "daily_calories",
            "data": {
                "date": target_date,
                "calories": data["total_calories"],
                "protein_g": data["total_protein_g"],
                "carbs_g": data["total_carbs_g"],
                "fat_g": data["total_fat_g"],
                "calories_burned": calories_burned,
                "net_calories": net_calories,
            },
        }

    raise HTTPException(status_code=404, detail=f"Unknown data_id: {data_id}")


# ---------------------------------------------------------------------------
# Summary (optional contract endpoint)
# ---------------------------------------------------------------------------

@router.get("/summary")
def get_summary(
    authorization: Optional[str] = Header(None),
    token: _TokenData = Depends(require_token),
) -> dict:
    """Return a natural language nutrition summary for AI briefings."""
    today = str(datetime.today().date())
    data = _day_totals(token.user_id, today)
    cal = data["total_calories"]
    meals = len(data["meals"])
    protein = data["total_protein_g"]
    carbs = data["total_carbs_g"]
    fat = data["total_fat_g"]
    calories_burned = _fetch_calories_burned(authorization or "", today)
    net_calories = (cal - calories_burned) if calories_burned is not None else None

    if meals == 0:
        text = f"No meals logged today ({today})."
    else:
        meal_word = "meal" if meals == 1 else "meals"
        text = (
            f"Today ({today}) you've logged {meals} {meal_word} totalling {cal} calories "
            f"({protein}g protein, {carbs}g carbs, {fat}g fat)."
        )
        if calories_burned is not None:
            text += f" Burned {calories_burned} cal from workouts; net {net_calories} cal."

    return {
        "module_id": "meal-planner",
        "summary": text,
        "data": {
            "date": today,
            "calories": cal,
            "protein_g": protein,
            "carbs_g": carbs,
            "fat_g": fat,
            "meals_logged": meals,
            "calories_burned": calories_burned,
            "net_calories": net_calories,
        },
    }


# ---------------------------------------------------------------------------
# Calendar (optional contract endpoint)
# ---------------------------------------------------------------------------

@router.get("/calendar")
def get_calendar(token: _TokenData = Depends(require_token)) -> dict:
    """Return upcoming meal events for the next 14 days."""
    today = datetime.today().date()
    window_end = today + timedelta(days=14)

    rows = _q(
        "SELECT id, name, date, meal_type, notes FROM meals WHERE user_id = %s AND date >= %s AND date <= %s ORDER BY date ASC LIMIT 20",
        (token.user_id, str(today), str(window_end)),
    )

    events = []
    for row in rows:
        events.append({
            "id": str(row.get("id", uuid.uuid4())),
            "title": row.get("name") or "Meal",
            "date": str(row["date"]),
            "type": "meal",
            "priority": "medium",
            "notes": row.get("meal_type") or None,
        })

    return {
        "module_id": "meal-planner",
        "events": events,
        "window_days": 14,
    }
