from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional, List
from core.database import get_db, get_cursor, USE_SQLITE
from core.logging_config import get_logger
import metrics
from core.auth_service import TokenData
from routers.auth import get_current_user
import json

log = get_logger("api.workouts")

router = APIRouter(prefix="/workouts", tags=["workouts"])

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
    return dict(row)

def serialize_json_fields(workout: dict) -> dict:
    """Convert list fields to JSON strings for storage"""
    result = dict(workout)
    for field in ['warmup', 'main', 'cooldown']:
        if field in result and result[field] is not None:
            if isinstance(result[field], (list, dict)):
                result[field] = json.dumps(result[field])
    return result

def deserialize_json_fields(row: dict) -> dict:
    """Convert JSON string fields back to lists"""
    if row is None:
        return None
    result = dict(row)
    for field in ['warmup', 'main', 'cooldown']:
        if field in result and result[field] is not None:
            if isinstance(result[field], str):
                try:
                    result[field] = json.loads(result[field])
                except json.JSONDecodeError:
                    result[field] = []
    return result


class WorkoutCreate(BaseModel):
    user_id: str
    name: str
    type: str
    warmup: Optional[List[dict]] = None
    main: Optional[List[dict]] = None
    cooldown: Optional[List[dict]] = None
    notes: Optional[str] = None
    status: Optional[str] = 'active'


class WorkoutUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    warmup: Optional[List[dict]] = None
    main: Optional[List[dict]] = None
    cooldown: Optional[List[dict]] = None
    notes: Optional[str] = None
    status: Optional[str] = None


@router.get("")
def get_workouts(user_id: str, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    with get_db() as conn:
        cur = get_cursor(conn)
        query, params = adapt_query(
            "SELECT * FROM workouts WHERE user_id = %s AND status != 'deleted' ORDER BY updated_at DESC",
            (user_id,)
        )
        cur.execute(query, params)
        rows = [deserialize_json_fields(dict_from_row(row)) for row in cur.fetchall()]
        log.info("workouts_list", extra={"user_id": user_id, "count": len(rows)})
        metrics.record_domain_event("workouts_list")
        return rows


@router.post("")
def create_workout(workout: WorkoutCreate, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != workout.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    log.info("workout_create_attempt", extra={"user_id": workout.user_id, "type": workout.type})
    metrics.record_domain_event("workout_create_attempt")

    # Serialize JSON fields
    warmup_json = json.dumps(workout.warmup) if workout.warmup else None
    main_json = json.dumps(workout.main) if workout.main else None
    cooldown_json = json.dumps(workout.cooldown) if workout.cooldown else None

    with get_db() as conn:
        cur = get_cursor(conn)
        query, params = adapt_query(
            """INSERT INTO workouts (user_id, name, type, warmup, main, cooldown, notes, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (workout.user_id, workout.name, workout.type, warmup_json, main_json, cooldown_json, workout.notes, workout.status)
        )
        cur.execute(query, params)

        if USE_SQLITE:
            cur.execute("SELECT * FROM workouts WHERE id = ?", (cur.lastrowid,))
            created = deserialize_json_fields(dict_from_row(cur.fetchone()))
        else:
            created = deserialize_json_fields(dict_from_row(cur.fetchone()))

    if created:
        log.info("workout_created", extra={"user_id": created.get("user_id"), "workout_id": created.get("id"), "type": created.get("type")})
        metrics.record_domain_event("workout_created")
    return created


@router.get("/{workout_id}")
def get_workout(workout_id: int, user_id: str, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    with get_db() as conn:
        cur = get_cursor(conn)
        query, params = adapt_query(
            "SELECT * FROM workouts WHERE id = %s AND user_id = %s",
            (workout_id, user_id)
        )
        cur.execute(query, params)
        workout = cur.fetchone()
        if not workout:
            raise HTTPException(status_code=404, detail="Workout not found")
        result = deserialize_json_fields(dict_from_row(workout))
        log.info("workout_retrieved", extra={"workout_id": workout_id})
        metrics.record_domain_event("workout_retrieved")
        return result


@router.put("/{workout_id}")
def update_workout(workout_id: int, workout: WorkoutUpdate, current_user: TokenData = Depends(get_current_user)):
    # Build updates dict, serializing JSON fields
    updates = {}
    workout_dict = workout.dict()
    for k, v in workout_dict.items():
        if v is not None:
            if k in ['warmup', 'main', 'cooldown']:
                updates[k] = json.dumps(v) if isinstance(v, (list, dict)) else v
            else:
                updates[k] = v

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Add updated_at
    updates['updated_at'] = 'CURRENT_TIMESTAMP'

    placeholder = "?" if USE_SQLITE else "%s"
    set_parts = []
    values = []
    for k, v in updates.items():
        if v == 'CURRENT_TIMESTAMP':
            set_parts.append(f"{k} = CURRENT_TIMESTAMP")
        else:
            set_parts.append(f"{k} = {placeholder}")
            values.append(v)

    set_clause = ", ".join(set_parts)
    values.append(workout_id)

    with get_db() as conn:
        cur = get_cursor(conn)
        if USE_SQLITE:
            cur.execute(f"UPDATE workouts SET {set_clause} WHERE id = {placeholder}", values)
            cur.execute("SELECT * FROM workouts WHERE id = ?", (workout_id,))
            updated = cur.fetchone()
        else:
            cur.execute(f"UPDATE workouts SET {set_clause} WHERE id = {placeholder} RETURNING *", values)
            updated = cur.fetchone()

        if not updated:
            raise HTTPException(status_code=404, detail="Workout not found")
        result = deserialize_json_fields(dict_from_row(updated))
        log.info("workout_updated", extra={"workout_id": workout_id, "fields": list(updates.keys())})
        metrics.record_domain_event("workout_updated")
        return result


@router.delete("/{workout_id}")
def delete_workout(workout_id: int, user_id: str, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    with get_db() as conn:
        cur = get_cursor(conn)
        # Soft delete by setting status to 'deleted'
        query, params = adapt_query(
            "UPDATE workouts SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s AND user_id = %s",
            ('deleted', workout_id, user_id)
        )
        cur.execute(query, params)
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Workout not found")
        log.info("workout_deleted", extra={"workout_id": workout_id, "user_id": user_id})
        metrics.record_domain_event("workout_deleted")
        return {"deleted": workout_id}


@router.get("/type/{workout_type}")
def get_workouts_by_type(workout_type: str, user_id: str, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    with get_db() as conn:
        cur = get_cursor(conn)
        query, params = adapt_query(
            "SELECT * FROM workouts WHERE user_id = %s AND type = %s AND status != 'deleted' ORDER BY updated_at DESC",
            (user_id, workout_type)
        )
        cur.execute(query, params)
        rows = [deserialize_json_fields(dict_from_row(row)) for row in cur.fetchall()]
        log.info("workouts_by_type", extra={"user_id": user_id, "type": workout_type, "count": len(rows)})
        metrics.record_domain_event("workouts_by_type")
        return rows
