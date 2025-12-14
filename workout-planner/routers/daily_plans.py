from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from database import get_db, get_cursor, USE_SQLITE
from auth_service import TokenData
from routers.auth import get_current_user
from logging_config import get_logger
import metrics

log = get_logger("api.daily_plans")
import json
from datetime import date

router = APIRouter(prefix="/daily-plans", tags=["daily-plans"])

def adapt_query(query: str, params: tuple):
    """Adapt PostgreSQL query to SQLite if needed"""
    if USE_SQLITE:
        query = query.replace("%s", "?")
        if "RETURNING *" in query:
            query = query.replace(" RETURNING *", "")
    return query, params

def dict_from_row(row):
    """Convert row to dict for both SQLite and PostgreSQL"""
    if row is None:
        return None
    if USE_SQLITE:
        return dict(row)
    return dict(row)


# ============================================================
# Models
# ============================================================

class Workout(BaseModel):
    """A single workout within a daily plan."""
    name: Optional[str] = None  # e.g., "Morning Run", "Strength Session"
    type: Optional[str] = None  # e.g., "strength", "run", "swim", "murph"
    warmup: List[dict] = Field(default_factory=list)  # List of exercises
    main: List[dict] = Field(default_factory=list)  # Main workout exercises
    cooldown: List[dict] = Field(default_factory=list)  # Cooldown exercises
    notes: Optional[str] = ""
    status: str = "pending"  # pending, complete, skipped

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        allowed = ['pending', 'complete', 'skipped']
        if v not in allowed:
            raise ValueError(f'status must be one of {allowed}')
        return v


class DailyPlanData(BaseModel):
    """A daily plan containing 1-3 workouts."""
    user_id: str
    date: str  # ISO date format
    workouts: List[Workout] = Field(default_factory=list, max_length=3)
    ai_notes: Optional[str] = None

    @field_validator('workouts')
    @classmethod
    def validate_workouts_count(cls, v):
        if len(v) > 3:
            raise ValueError('A daily plan can have at most 3 workouts')
        return v


class DailyPlanResponse(BaseModel):
    """Response model for daily plan."""
    user_id: str
    date: str
    workouts: List[Workout]
    ai_notes: Optional[str] = None


# ============================================================
# Helper functions for backward compatibility
# ============================================================

def migrate_old_format_to_new(plan_json: dict) -> List[dict]:
    """Convert old flat format to new workouts array format."""
    # Check if already in new format
    if 'workouts' in plan_json:
        return plan_json['workouts']

    # Convert old format (warmup, main, cooldown at top level) to new format
    workout = {
        'name': 'Workout',
        'type': None,
        'warmup': plan_json.get('warmup', []),
        'main': plan_json.get('main', []),
        'cooldown': plan_json.get('cooldown', []),
        'notes': plan_json.get('notes', ''),
        'status': 'pending'
    }
    return [workout]


def build_response(user_id: str, plan_date: str, workouts: List[dict], ai_notes: Optional[str] = None) -> dict:
    """Build a consistent response dictionary."""
    return {
        "user_id": user_id,
        "date": plan_date,
        "workouts": workouts,
        "ai_notes": ai_notes
    }


# ============================================================
# API Endpoints
# ============================================================

@router.get("/{user_id}/{plan_date}")
def get_daily_plan(user_id: str, plan_date: str, current_user: TokenData = Depends(get_current_user)):
    """Get user's daily plan for specified date."""
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")

    with get_db() as conn:
        cur = get_cursor(conn)

        query, params = adapt_query(
            "SELECT * FROM daily_plans WHERE user_id = %s AND date = %s",
            (user_id, plan_date)
        )

        cur.execute(query, params)
        row = cur.fetchone()

        if not row:
            # Return default empty plan with one empty workout
            default_workout = {
                "name": "Workout",
                "type": None,
                "warmup": [],
                "main": [],
                "cooldown": [],
                "notes": "",
                "status": "pending"
            }
            result = build_response(user_id, plan_date, [default_workout], None)
            log.info("daily_plan_default", extra={"user_id": user_id, "date": plan_date})
            metrics.record_domain_event("daily_plan_default")
            return result

        result = dict_from_row(row)

        # Parse plan_json if it's a string (SQLite stores JSON as text)
        if isinstance(result.get('plan_json'), str):
            result['plan_json'] = json.loads(result['plan_json'])

        # Migrate old format if needed
        workouts = migrate_old_format_to_new(result['plan_json'])

        # If old format had a status at the plan level, apply it to the first workout
        if 'status' in result and result['status'] and workouts:
            # Only apply if the workout doesn't already have a non-pending status
            if workouts[0].get('status', 'pending') == 'pending':
                workouts[0]['status'] = result['status']

        response = build_response(
            user_id=result['user_id'],
            plan_date=str(result['date']),
            workouts=workouts,
            ai_notes=result.get('ai_notes')
        )

        log.info("daily_plan_retrieved", extra={
            "user_id": user_id,
            "date": plan_date,
            "workout_count": len(workouts)
        })
        metrics.record_domain_event("daily_plan_retrieved")
        return response


@router.put("/{user_id}/{plan_date}")
def update_daily_plan(user_id: str, plan_date: str, plan: DailyPlanData, current_user: TokenData = Depends(get_current_user)):
    """Create or update user's daily plan."""
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")

    # Validate workout count
    if len(plan.workouts) > 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A daily plan can have at most 3 workouts"
        )

    with get_db() as conn:
        cur = get_cursor(conn)

        # Store workouts in the new format
        plan_json = {
            "workouts": [w.model_dump() for w in plan.workouts]
        }
        plan_json_str = json.dumps(plan_json)

        # Compute overall status based on workouts
        # If all workouts complete -> complete, if any skipped and rest complete/skipped -> skipped, else pending
        statuses = [w.status for w in plan.workouts] if plan.workouts else ['pending']
        if all(s == 'complete' for s in statuses):
            overall_status = 'complete'
        elif all(s in ('complete', 'skipped') for s in statuses):
            overall_status = 'skipped' if any(s == 'skipped' for s in statuses) else 'complete'
        else:
            overall_status = 'pending'

        if USE_SQLITE:
            query = """
                INSERT INTO daily_plans (user_id, date, plan_json, status, ai_notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, date)
                DO UPDATE SET
                    plan_json = excluded.plan_json,
                    status = excluded.status,
                    ai_notes = excluded.ai_notes
            """
            params = (user_id, plan_date, plan_json_str, overall_status, plan.ai_notes)
        else:
            query = """
                INSERT INTO daily_plans (user_id, date, plan_json, status, ai_notes)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, date)
                DO UPDATE SET
                    plan_json = EXCLUDED.plan_json,
                    status = EXCLUDED.status,
                    ai_notes = EXCLUDED.ai_notes
                RETURNING *
            """
            params = (user_id, plan_date, plan_json_str, overall_status, plan.ai_notes)

        cur.execute(query, params)
        conn.commit()

        response = build_response(
            user_id=user_id,
            plan_date=plan_date,
            workouts=[w.model_dump() for w in plan.workouts],
            ai_notes=plan.ai_notes
        )
        response["message"] = "Daily plan saved successfully"

        log.info("daily_plan_saved", extra={
            "user_id": user_id,
            "date": plan_date,
            "workout_count": len(plan.workouts)
        })
        metrics.record_domain_event("daily_plan_saved")
        return response


@router.delete("/{user_id}/{plan_date}")
def delete_daily_plan(user_id: str, plan_date: str, current_user: TokenData = Depends(get_current_user)):
    """Delete user's daily plan."""
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")

    with get_db() as conn:
        cur = get_cursor(conn)

        query, params = adapt_query(
            "DELETE FROM daily_plans WHERE user_id = %s AND date = %s",
            (user_id, plan_date)
        )

        cur.execute(query, params)
        conn.commit()

        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Daily plan not found")

        log.info("daily_plan_deleted", extra={"user_id": user_id, "date": plan_date})
        metrics.record_domain_event("daily_plan_deleted")
        return {"message": "Daily plan deleted successfully"}


# ============================================================
# Individual Workout Endpoints (convenience methods)
# ============================================================

@router.patch("/{user_id}/{plan_date}/workouts/{workout_index}")
def update_workout_status(
    user_id: str,
    plan_date: str,
    workout_index: int,
    status_update: dict,
    current_user: TokenData = Depends(get_current_user)
):
    """Update a specific workout's status within a daily plan."""
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")

    new_status = status_update.get('status')
    if new_status not in ['pending', 'complete', 'skipped']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be 'pending', 'complete', or 'skipped'"
        )

    with get_db() as conn:
        cur = get_cursor(conn)

        # Get existing plan
        query, params = adapt_query(
            "SELECT * FROM daily_plans WHERE user_id = %s AND date = %s",
            (user_id, plan_date)
        )
        cur.execute(query, params)
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Daily plan not found")

        result = dict_from_row(row)
        if isinstance(result.get('plan_json'), str):
            result['plan_json'] = json.loads(result['plan_json'])

        workouts = migrate_old_format_to_new(result['plan_json'])

        if workout_index < 0 or workout_index >= len(workouts):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Workout index {workout_index} out of range (0-{len(workouts)-1})"
            )

        # Update the specific workout's status
        workouts[workout_index]['status'] = new_status

        # Also update notes if provided
        if 'notes' in status_update:
            workouts[workout_index]['notes'] = status_update['notes']

        # Save back
        plan_json = {"workouts": workouts}
        plan_json_str = json.dumps(plan_json)

        # Compute overall status
        statuses = [w.get('status', 'pending') for w in workouts]
        if all(s == 'complete' for s in statuses):
            overall_status = 'complete'
        elif all(s in ('complete', 'skipped') for s in statuses):
            overall_status = 'skipped' if any(s == 'skipped' for s in statuses) else 'complete'
        else:
            overall_status = 'pending'

        if USE_SQLITE:
            update_query = """
                UPDATE daily_plans SET plan_json = ?, status = ?
                WHERE user_id = ? AND date = ?
            """
            cur.execute(update_query, (plan_json_str, overall_status, user_id, plan_date))
        else:
            update_query = """
                UPDATE daily_plans SET plan_json = %s, status = %s
                WHERE user_id = %s AND date = %s
            """
            cur.execute(update_query, (plan_json_str, overall_status, user_id, plan_date))

        conn.commit()

        log.info("workout_status_updated", extra={
            "user_id": user_id,
            "date": plan_date,
            "workout_index": workout_index,
            "new_status": new_status
        })
        metrics.record_domain_event("workout_status_updated")

        return {
            "message": f"Workout {workout_index} status updated to {new_status}",
            "workout": workouts[workout_index]
        }
