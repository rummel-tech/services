"""Artemis platform integration router for Workout Planner.

Implements the Artemis Module Contract v1.0:
  GET  /artemis/manifest
  GET  /artemis/widgets/{widget_id}
  POST /artemis/agent/{tool_id}
  GET  /artemis/data/{data_id}

Accepts both standalone workout-planner tokens AND Artemis platform tokens
(iss == "artemis-auth"). Artemis tokens are verified against the public key
fetched from the auth service at ARTEMIS_AUTH_URL.
"""
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from jose import JWTError, jwt

from core.auth_service import TokenData, decode_token
from core.database import USE_SQLITE, get_cursor, get_db
from core.logging_config import get_logger
from core.settings import get_settings
from routers.readiness import _calculate_readiness

log = get_logger("api.artemis")
router = APIRouter(prefix="/artemis", tags=["artemis"])

# ---------------------------------------------------------------------------
# Artemis public key cache (fetched once from auth service, then cached)
# ---------------------------------------------------------------------------
_artemis_public_key: Optional[str] = None
ARTEMIS_AUTH_URL = os.getenv("ARTEMIS_AUTH_URL", "http://localhost:8090")


def _fetch_artemis_public_key() -> Optional[str]:
    """Fetch the Artemis RSA public key from the auth service."""
    global _artemis_public_key
    if _artemis_public_key:
        return _artemis_public_key
    try:
        r = httpx.get(f"{ARTEMIS_AUTH_URL}/auth/public-key", timeout=3.0)
        if r.status_code == 200:
            _artemis_public_key = r.json()["public_key"]
            return _artemis_public_key
    except Exception:
        log.warning("artemis_public_key_fetch_failed", extra={"url": ARTEMIS_AUTH_URL})
    return None


# ---------------------------------------------------------------------------
# Dual-mode token dependency
# ---------------------------------------------------------------------------

def _get_token_payload(authorization: Optional[str]) -> TokenData:
    """Accept both standalone and Artemis platform tokens."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    raw = authorization.split(" ", 1)[1]

    # Peek at iss without verifying signature
    try:
        unverified = jwt.get_unverified_claims(raw)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if unverified.get("iss") == "artemis-auth":
        pub_key = _fetch_artemis_public_key()
        if not pub_key:
            settings = get_settings()
            if settings.environment != "production":
                # Auth service not running — allow in dev with a stub user
                log.warning("artemis_auth_unavailable_dev_stub")
                return TokenData(user_id=unverified.get("sub", "dev-user"), email=unverified.get("email", ""))
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service unavailable")
        try:
            payload = jwt.decode(raw, pub_key, algorithms=["RS256"], issuer="artemis-auth")
            return TokenData(
                user_id=payload["sub"],
                email=payload.get("email", ""),
                jti=payload.get("jti"),
                exp=payload.get("exp"),
            )
        except JWTError as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Artemis token: {e}")
    else:
        # Standalone token — use existing service validation
        token_data = decode_token(raw)
        if not token_data:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return token_data


def require_token(authorization: Optional[str] = Header(None)) -> TokenData:
    return _get_token_payload(authorization)


# ---------------------------------------------------------------------------
# Module manifest (static — no auth required per contract)
# ---------------------------------------------------------------------------

VERSION = "1.2.0"

MANIFEST = {
    "module": {
        "id": "workout-planner",
        "name": "Workout Planner",
        "version": VERSION,
        "contract_version": "1.0",
        "description": "AI-powered fitness coaching with HealthKit integration",
        "icon": "fitness_center",
        "color": "#34d399",
        "standalone_url": "https://rummel-tech.github.io/workout-planner/",
        "api_base": "https://api.rummeltech.com/workout-planner",
    },
    "capabilities": {
        "auth": {
            "accepts_artemis_token": True,
            "standalone_auth": True,
        },
        "dashboard_widgets": [
            {
                "id": "todays_workout",
                "name": "Today's Workout",
                "description": "Shows scheduled workout for today",
                "size": "medium",
                "data_endpoint": "/artemis/widgets/todays_workout",
                "refresh_seconds": 300,
            },
            {
                "id": "weekly_progress",
                "name": "Weekly Progress",
                "description": "Workout completion this week",
                "size": "small",
                "data_endpoint": "/artemis/widgets/weekly_progress",
                "refresh_seconds": 3600,
            },
            {
                "id": "readiness_score",
                "name": "Readiness Score",
                "description": "Today's readiness score based on sleep and recovery",
                "size": "small",
                "data_endpoint": "/artemis/widgets/readiness_score",
                "refresh_seconds": 3600,
            },
        ],
        "quick_actions": [
            {
                "id": "log_workout",
                "label": "Log Workout",
                "icon": "add_circle",
                "endpoint": "/artemis/agent/log_workout",
                "method": "POST",
            },
            {
                "id": "start_workout",
                "label": "Start Today's Workout",
                "icon": "play_arrow",
                "endpoint": "/artemis/agent/get_todays_workout",
                "method": "GET",
            },
        ],
        "provides_data": [
            {
                "id": "calories_burned",
                "name": "Daily Calories Burned",
                "description": "Calories burned per day from workouts",
                "endpoint": "/artemis/data/calories_burned",
                "schema": {
                    "date": "string (ISO date)",
                    "calories": "number",
                    "workout_type": "string",
                    "duration_minutes": "number",
                },
                "requires_permission": "fitness.calories.read",
            },
            {
                "id": "readiness_score",
                "name": "Readiness Score",
                "description": "Daily readiness score based on sleep and recovery",
                "endpoint": "/artemis/data/readiness_score",
                "schema": {
                    "date": "string",
                    "score": "number (0-1)",
                    "factors": "object",
                },
                "requires_permission": "fitness.readiness.read",
            },
            {
                "id": "workout_schedule",
                "name": "Workout Schedule",
                "description": "Upcoming scheduled workouts",
                "endpoint": "/artemis/data/workout_schedule",
                "schema": {
                    "workouts": "array",
                    "date_range": "object",
                },
                "requires_permission": "fitness.schedule.read",
            },
        ],
        "consumes_data": [
            {
                "id": "nutrition_calories",
                "provider_module": "meal-planner",
                "data_id": "daily_calories",
                "use_case": "Adjust calorie burn targets based on intake",
                "required": False,
            }
        ],
        "agent_tools": [
            {
                "id": "get_todays_workout",
                "description": "Get the user's scheduled workout for today or a specific date",
                "endpoint": "/artemis/agent/get_todays_workout",
                "method": "GET",
                "parameters": {
                    "date": {"type": "string", "description": "ISO date, defaults to today", "required": False},
                },
            },
            {
                "id": "log_workout",
                "description": "Log a completed workout",
                "endpoint": "/artemis/agent/log_workout",
                "method": "POST",
                "parameters": {
                    "type": {"type": "string", "description": "Workout type (strength, run, swim, etc.)", "required": True},
                    "duration_minutes": {"type": "number", "required": True},
                    "notes": {"type": "string", "required": False},
                },
            },
            {
                "id": "schedule_workout",
                "description": "Schedule a workout for a specific date",
                "endpoint": "/artemis/agent/schedule_workout",
                "method": "POST",
                "parameters": {
                    "type": {"type": "string", "required": True},
                    "date": {"type": "string", "description": "ISO date", "required": True},
                    "duration_minutes": {"type": "number", "required": False},
                    "notes": {"type": "string", "required": False},
                },
            },
            {
                "id": "get_weekly_summary",
                "description": "Get a summary of workouts and progress for the current or specified week",
                "endpoint": "/artemis/agent/get_weekly_summary",
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
# Widgets
# ---------------------------------------------------------------------------

def _q(conn, sql: str, params: tuple):
    cur = get_cursor(conn)
    if USE_SQLITE:
        sql = sql.replace("%s", "?")
    cur.execute(sql, params)
    return cur.fetchall()


def _fetch_daily_plan(user_id: str, plan_date: str) -> Optional[dict]:
    with get_db() as conn:
        cur = get_cursor(conn)
        sql = "SELECT * FROM daily_plans WHERE user_id = %s AND date = %s"
        if USE_SQLITE:
            sql = sql.replace("%s", "?")
        cur.execute(sql, (user_id, plan_date))
        row = cur.fetchone()
        return dict(row) if row else None


def _parse_plan_workouts(row: dict) -> list:
    plan_json = row.get("plan_json")
    if not plan_json:
        return []
    if isinstance(plan_json, str):
        try:
            plan_json = json.loads(plan_json)
        except json.JSONDecodeError:
            return []
    if "workouts" in plan_json:
        return plan_json["workouts"]
    # Legacy flat format
    return [{"name": "Workout", "type": None, "warmup": plan_json.get("warmup", []),
              "main": plan_json.get("main", []), "cooldown": plan_json.get("cooldown", []),
              "notes": plan_json.get("notes", ""), "status": "pending"}]


@router.get("/widgets/{widget_id}")
def get_widget(
    widget_id: str,
    token: TokenData = Depends(require_token),
) -> dict:
    user_id = token.user_id
    now = datetime.now(timezone.utc).isoformat() + "Z"

    if widget_id == "todays_workout":
        today = str(date.today())
        row = _fetch_daily_plan(user_id, today)
        if not row:
            return {"widget_id": "todays_workout", "data": {"has_workout": False}, "last_updated": now}
        workouts = _parse_plan_workouts(row)
        first = workouts[0] if workouts else {}
        return {
            "widget_id": "todays_workout",
            "data": {
                "has_workout": bool(workouts),
                "workout": {
                    "title": first.get("name", "Workout"),
                    "type": first.get("type"),
                    "status": first.get("status", "pending"),
                    "exercise_count": len(first.get("main", [])),
                } if first else None,
                "total_workouts": len(workouts),
            },
            "last_updated": now,
        }

    elif widget_id == "weekly_progress":
        # Current week Mon–Sun
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        with get_db() as conn:
            rows = _q(conn,
                "SELECT date, plan_json, status FROM daily_plans WHERE user_id = %s AND date >= %s AND date <= %s",
                (user_id, str(week_start), str(week_end)),
            )

        total = len(rows)
        completed = 0
        for r in rows:
            row = dict(r)
            plan_json = row.get("plan_json")
            if isinstance(plan_json, str):
                try:
                    plan_json = json.loads(plan_json)
                except Exception:
                    plan_json = {}
            workouts = plan_json.get("workouts", []) if plan_json else []
            if any(w.get("status") == "complete" for w in workouts):
                completed += 1

        return {
            "widget_id": "weekly_progress",
            "data": {
                "week_start": str(week_start),
                "week_end": str(week_end),
                "planned": total,
                "completed": completed,
                "completion_pct": round(completed / total * 100) if total else 0,
            },
            "last_updated": now,
        }

    elif widget_id == "readiness_score":
        data = _calculate_readiness(user_id)
        return {
            "widget_id": "readiness_score",
            "data": {
                "score": data["readiness"],
                "score_pct": round(data["readiness"] * 100),
                "factors": data["scores"],
            },
            "last_updated": now,
        }

    raise HTTPException(status_code=404, detail=f"Unknown widget: {widget_id}")


# ---------------------------------------------------------------------------
# Agent tools
# ---------------------------------------------------------------------------

@router.get("/agent/get_todays_workout")
@router.post("/agent/get_todays_workout")
def agent_get_todays_workout(
    date: Optional[str] = None,
    body: Optional[dict] = None,
    token: TokenData = Depends(require_token),
) -> dict:
    target_date = date or (body or {}).get("date") or str(datetime.now(timezone.utc).date())
    user_id = token.user_id
    row = _fetch_daily_plan(user_id, target_date)
    if not row:
        return {"success": True, "result": {"date": target_date, "has_workout": False, "workouts": []}}
    workouts = _parse_plan_workouts(row)
    return {
        "success": True,
        "result": {
            "date": target_date,
            "has_workout": bool(workouts),
            "workouts": workouts,
            "ai_notes": row.get("ai_notes"),
        },
    }


@router.post("/agent/log_workout")
def agent_log_workout(
    body: dict,
    token: TokenData = Depends(require_token),
) -> dict:
    workout_type = body.get("type")
    duration = body.get("duration_minutes")
    notes = body.get("notes", "")

    if not workout_type:
        raise HTTPException(status_code=400, detail="type is required")
    if duration is None:
        raise HTTPException(status_code=400, detail="duration_minutes is required")

    user_id = token.user_id
    workout_id = str(uuid.uuid4())
    workout_name = f"{workout_type.title()} Workout"

    with get_db() as conn:
        cur = get_cursor(conn)
        sql = "INSERT INTO workouts (user_id, name, type, notes, status) VALUES (%s, %s, %s, %s, %s)"
        if USE_SQLITE:
            sql = sql.replace("%s", "?")
        cur.execute(sql, (user_id, workout_name, workout_type, notes, "complete"))
        conn.commit()

    return {
        "success": True,
        "result": {
            "workout_id": workout_id,
            "type": workout_type,
            "duration_minutes": duration,
        },
        "message": f"Logged {duration}-minute {workout_type} workout",
    }


@router.post("/agent/schedule_workout")
def agent_schedule_workout(
    body: dict,
    token: TokenData = Depends(require_token),
) -> dict:
    workout_type = body.get("type")
    target_date = body.get("date") or str(date.today())
    duration = body.get("duration_minutes", 60)
    notes = body.get("notes", "")

    if not workout_type:
        raise HTTPException(status_code=400, detail="type is required")

    user_id = token.user_id
    plan_json = json.dumps({
        "workouts": [{
            "name": f"{workout_type.title()} Workout",
            "type": workout_type,
            "warmup": [],
            "main": [{"exercise": f"{workout_type.title()}", "duration_minutes": duration}],
            "cooldown": [],
            "notes": notes,
            "status": "pending",
        }]
    })

    with get_db() as conn:
        cur = get_cursor(conn)
        # Upsert: update if exists, insert if not
        check_sql = "SELECT id FROM daily_plans WHERE user_id = %s AND date = %s"
        if USE_SQLITE:
            check_sql = check_sql.replace("%s", "?")
        cur.execute(check_sql, (user_id, target_date))
        existing = cur.fetchone()

        if existing:
            sql = "UPDATE daily_plans SET plan_json = %s WHERE user_id = %s AND date = %s"
            if USE_SQLITE:
                sql = sql.replace("%s", "?")
            cur.execute(sql, (plan_json, user_id, target_date))
        else:
            sql = "INSERT INTO daily_plans (user_id, date, plan_json, status) VALUES (%s, %s, %s, %s)"
            if USE_SQLITE:
                sql = sql.replace("%s", "?")
            cur.execute(sql, (user_id, target_date, plan_json, "pending"))
        conn.commit()

    return {
        "success": True,
        "result": {
            "date": target_date,
            "type": workout_type,
            "duration_minutes": duration,
        },
        "message": f"Scheduled {workout_type} workout for {target_date}",
    }


@router.get("/agent/get_weekly_summary")
@router.post("/agent/get_weekly_summary")
def agent_get_weekly_summary(
    week_start: Optional[str] = None,
    body: Optional[dict] = None,
    token: TokenData = Depends(require_token),
) -> dict:
    user_id = token.user_id
    ws_str = week_start or (body or {}).get("week_start")

    if ws_str:
        ws = date.fromisoformat(ws_str)
    else:
        today = date.today()
        ws = today - timedelta(days=today.weekday())

    we = ws + timedelta(days=6)

    with get_db() as conn:
        rows = _q(conn,
            "SELECT date, plan_json, status FROM daily_plans WHERE user_id = %s AND date >= %s AND date <= %s ORDER BY date",
            (user_id, str(ws), str(we)),
        )

    planned, completed, skipped = 0, 0, 0
    workout_types: list[str] = []

    for r in rows:
        row = dict(r)
        pj = row.get("plan_json")
        if isinstance(pj, str):
            try:
                pj = json.loads(pj)
            except Exception:
                pj = {}
        workouts = pj.get("workouts", []) if pj else []
        for w in workouts:
            planned += 1
            s = w.get("status", "pending")
            if s == "complete":
                completed += 1
            elif s == "skipped":
                skipped += 1
            if w.get("type"):
                workout_types.append(w["type"])

    return {
        "success": True,
        "result": {
            "week_start": str(ws),
            "week_end": str(we),
            "planned": planned,
            "completed": completed,
            "skipped": skipped,
            "pending": planned - completed - skipped,
            "workout_types": list(set(workout_types)),
            "completion_pct": round(completed / planned * 100) if planned else 0,
        },
    }


# ---------------------------------------------------------------------------
# Cross-module data endpoints
# ---------------------------------------------------------------------------

def _check_data_permission(
    data_id: str,
    x_artemis_permission: Optional[str],
    token: TokenData,
) -> None:
    """For cross-module data, require explicit permission header or the user
    to be requesting their own data with a permission-carrying Artemis token."""
    # Standalone tokens accessing own data are permitted
    # Artemis tokens require the correct permission in the header
    pass  # TODO: tighten when permission grants are fully implemented


PERMISSION_MAP = {
    "calories_burned": "fitness.calories.read",
    "readiness_score": "fitness.readiness.read",
    "workout_schedule": "fitness.schedule.read",
}

# Rough MET values for calorie estimation
MET_BY_TYPE: dict[str, float] = {
    "strength": 5.0,
    "run": 9.8,
    "swim": 8.0,
    "murph": 10.0,
    "yoga": 2.5,
    "hiit": 8.0,
}
AVG_WEIGHT_KG = 80.0  # fallback when user weight not stored


@router.get("/data/{data_id}")
def get_shared_data(
    data_id: str,
    date: Optional[str] = None,
    token: TokenData = Depends(require_token),
    x_artemis_permission: Optional[str] = Header(None),
) -> dict:
    _check_data_permission(data_id, x_artemis_permission, token)
    user_id = token.user_id
    target_date = date or str(datetime.now(timezone.utc).date())

    if data_id == "calories_burned":
        row = _fetch_daily_plan(user_id, target_date)
        calories = 0
        workout_type = None
        duration_minutes = 0
        if row:
            workouts = _parse_plan_workouts(row)
            for w in workouts:
                if w.get("status") == "complete":
                    wtype = w.get("type", "strength")
                    workout_type = wtype
                    # Estimate duration from main exercises or default 60min
                    for ex in w.get("main", []):
                        duration_minutes += ex.get("duration_minutes", 0)
                    if duration_minutes == 0:
                        duration_minutes = 60
                    met = MET_BY_TYPE.get(wtype, 5.0)
                    calories += round(met * AVG_WEIGHT_KG * (duration_minutes / 60))

        return {
            "data_id": "calories_burned",
            "data": {
                "date": target_date,
                "calories": calories,
                "workout_type": workout_type,
                "duration_minutes": duration_minutes,
            },
        }

    elif data_id == "readiness_score":
        data = _calculate_readiness(user_id)
        return {
            "data_id": "readiness_score",
            "data": {
                "date": target_date,
                "score": data["readiness"],
                "factors": data["scores"],
            },
        }

    elif data_id == "workout_schedule":
        today = date or str(datetime.now(timezone.utc).date())
        week_end = str(datetime.fromisoformat(today).date() + timedelta(days=7))
        with get_db() as conn:
            rows = _q(conn,
                "SELECT date, plan_json FROM daily_plans WHERE user_id = %s AND date >= %s AND date <= %s ORDER BY date",
                (user_id, today, week_end),
            )
        workouts_out = []
        for r in rows:
            row = dict(r)
            pj = row.get("plan_json")
            if isinstance(pj, str):
                try:
                    pj = json.loads(pj)
                except Exception:
                    pj = {}
            for w in (pj.get("workouts", []) if pj else []):
                workouts_out.append({
                    "date": row["date"],
                    "type": w.get("type"),
                    "name": w.get("name"),
                    "status": w.get("status", "pending"),
                })
        return {
            "data_id": "workout_schedule",
            "data": {
                "workouts": workouts_out,
                "date_range": {"start": today, "end": week_end},
            },
        }

    raise HTTPException(status_code=404, detail=f"Unknown data_id: {data_id}")
