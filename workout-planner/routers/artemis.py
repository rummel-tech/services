"""Artemis platform integration router for Workout Planner.

Accepts both standalone workout-planner tokens AND Artemis platform tokens
(iss == "artemis-auth") via the shared dual-token auth in common/.
"""
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from common.artemis_auth import create_artemis_token_dependency
from core.auth_service import TokenData, decode_token
from core.database import USE_SQLITE, get_cursor, get_db
from routers.readiness import _calculate_readiness

router = APIRouter(prefix="/artemis", tags=["artemis"])

require_token = create_artemis_token_dependency(
    standalone_decoder=decode_token,
    token_data_class=TokenData,
)


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
        "optional_endpoints": [
            {
                "path": "/artemis/summary",
                "description": "Natural language workout readiness and activity summary for AI briefings",
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
    """For cross-module data, require the caller to hold the correct permission.

    Rules:
    - Standalone token (no permissions list): allowed to access own data only.
    - Artemis token: must hold the specific permission for the requested data_id.
      The required permission is declared in PERMISSION_MAP.
    """
    required = PERMISSION_MAP.get(data_id)
    if required is None:
        # Unknown data_id — reject rather than silently permit
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown data type: {data_id}",
        )

    # Artemis tokens carry explicit permissions — enforce them
    if token.permissions:
        if required not in token.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Token missing required permission: {required}",
            )
        return

    # Standalone token: permit read of own data (no cross-module grant needed)
    # The router already ensures user_id scoping on queries, so this is safe.


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


# ---------------------------------------------------------------------------
# Summary (optional contract endpoint)
# ---------------------------------------------------------------------------

@router.get("/summary")
def get_summary(token: TokenData = Depends(require_token)) -> dict:
    """Return a natural language fitness summary for AI briefings."""
    user_id = token.user_id
    today = str(date.today())

    # Readiness score
    readiness_data = _calculate_readiness(user_id)
    readiness = readiness_data.get("readiness", 0.0)
    readiness_label = (
        "excellent" if readiness >= 0.8 else
        "good" if readiness >= 0.6 else
        "moderate" if readiness >= 0.4 else
        "low"
    )

    # Today's workout plan
    today_workout = None
    with get_db() as conn:
        rows = _q(conn, "SELECT plan_json FROM daily_plans WHERE user_id = %s AND date = %s LIMIT 1", (user_id, today))
        if rows:
            pj = rows[0]["plan_json"] if isinstance(rows[0], dict) else dict(rows[0]).get("plan_json")
            if isinstance(pj, str):
                try:
                    pj = json.loads(pj)
                except Exception:
                    pj = {}
            workouts = (pj or {}).get("workouts", [])
            if workouts:
                today_workout = workouts[0].get("name") or workouts[0].get("type")

    # Weekly streak
    week_start = date.today() - timedelta(days=date.today().weekday())
    with get_db() as conn:
        streak_rows = _q(
            conn,
            "SELECT COUNT(*) as cnt FROM daily_plans WHERE user_id = %s AND date >= %s AND date <= %s AND status = 'completed'",
            (user_id, str(week_start), today),
        )
    completed_this_week = streak_rows[0]["cnt"] if streak_rows else 0

    parts = [f"Readiness score: {round(readiness * 100)}% ({readiness_label})."]
    if today_workout:
        parts.append(f"Today's workout: {today_workout}.")
    else:
        parts.append("No workout planned for today.")
    if completed_this_week:
        parts.append(f"{completed_this_week} workout{'s' if completed_this_week != 1 else ''} completed this week.")

    return {
        "module_id": "workout-planner",
        "summary": " ".join(parts),
        "data": {
            "date": today,
            "readiness_score": readiness,
            "readiness_label": readiness_label,
            "todays_workout": today_workout,
            "workouts_completed_this_week": completed_this_week,
        },
    }


# ---------------------------------------------------------------------------
# Calendar (optional contract endpoint)
# ---------------------------------------------------------------------------

@router.get("/calendar")
def get_calendar(token: TokenData = Depends(require_token)) -> dict:
    """Return upcoming workout events for the next 14 days."""
    user_id = token.user_id
    today = datetime.today().date()
    window_end = today + timedelta(days=14)

    with get_db() as conn:
        rows = _q(
            conn,
            "SELECT id, date, plan_json FROM daily_plans WHERE user_id = %s AND date >= %s AND date <= %s ORDER BY date ASC",
            (user_id, str(today), str(window_end)),
        )

    events = []
    for r in rows:
        row = dict(r)
        pj = row.get("plan_json")
        if isinstance(pj, str):
            try:
                pj = json.loads(pj)
            except Exception:
                pj = {}
        workouts = (pj or {}).get("workouts", [])
        if not workouts:
            workouts = [{"name": "Workout", "type": None, "notes": ""}]
        for w in workouts:
            events.append({
                "id": str(row.get("id", uuid.uuid4())),
                "title": w.get("name") or w.get("type") or "Workout",
                "date": str(row["date"]),
                "type": "workout",
                "priority": "medium",
                "notes": w.get("notes") or None,
            })
        if len(events) >= 20:
            break

    return {
        "module_id": "workout-planner",
        "events": events[:20],
        "window_days": 14,
    }
