from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from database import get_db, get_cursor, USE_SQLITE
from auth_service import TokenData
from routers.auth import get_current_user
from logging_config import get_logger
import metrics

log = get_logger("api.weekly_plans")
import json
from datetime import date

router = APIRouter(prefix="/weekly-plans", tags=["weekly-plans"])

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

class WeeklyPlanData(BaseModel):
    user_id: str
    week_start: Optional[str] = None  # ISO date, defaults to current week
    focus: Optional[str] = None
    days: list  # List of {day, type}

@router.get("/{user_id}")
def get_weekly_plan(user_id: str, week_start: Optional[str] = None, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    """Get user's weekly plan for specified week (or current week)"""
    with get_db() as conn:
        cur = get_cursor(conn)
        
        # If no week_start provided, get the most recent plan
        if week_start:
            query, params = adapt_query(
                "SELECT * FROM weekly_plans WHERE user_id = %s AND week_start = %s",
                (user_id, week_start)
            )
        else:
            query, params = adapt_query(
                "SELECT * FROM weekly_plans WHERE user_id = %s ORDER BY week_start DESC LIMIT 1",
                (user_id,)
            )
        
        cur.execute(query, params)
        row = cur.fetchone()
        
        if not row:
            # Return default plan structure
            result = {
                "user_id": user_id,
                "week_start": week_start or str(date.today()),
                "focus": "hybrid",
                "days": [
                    {"day": "Monday", "type": "Strength"},
                    {"day": "Tuesday", "type": "Run"},
                    {"day": "Wednesday", "type": "Swim"},
                    {"day": "Thursday", "type": "Strength"},
                    {"day": "Friday", "type": "Murph"},
                    {"day": "Saturday", "type": "Run"},
                    {"day": "Sunday", "type": "Rest"}
                ]
            }
            log.info("weekly_plan_default", extra={"user_id": user_id, "week_start": result["week_start"], "days": len(result["days"])})
            metrics.record_domain_event("weekly_plan_default")
            return result
        
        result = dict_from_row(row)
        
        # Parse plan_json if it's a string (SQLite stores JSON as text)
        if isinstance(result.get('plan_json'), str):
            result['plan_json'] = json.loads(result['plan_json'])
        
        # Return in the format expected by the Flutter app
        response = {
            "user_id": result['user_id'],
            "week_start": str(result['week_start']),
            "focus": result.get('focus', 'hybrid'),
            "days": result.get('plan_json', {}).get('days', [])
        }
        log.info("weekly_plan_retrieved", extra={"user_id": user_id, "week_start": response["week_start"], "days": len(response["days"])})
        metrics.record_domain_event("weekly_plan_retrieved")
        return response

@router.put("/{user_id}")
def save_weekly_plan(user_id: str, plan: WeeklyPlanData, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    """Save or update user's weekly plan"""
    week_start = plan.week_start or str(date.today())
    
    # Prepare plan_json
    plan_json = {"days": plan.days}
    
    with get_db() as conn:
        cur = get_cursor(conn)
        
        if USE_SQLITE:
            # SQLite: INSERT OR REPLACE
            query = """INSERT OR REPLACE INTO weekly_plans 
                      (user_id, week_start, focus, plan_json)
                      VALUES (?, ?, ?, ?)"""
            cur.execute(query, (user_id, week_start, plan.focus, json.dumps(plan_json)))
            
            # Fetch the inserted/updated row
            cur.execute("SELECT * FROM weekly_plans WHERE user_id = ? AND week_start = ?",
                       (user_id, week_start))
            result = dict_from_row(cur.fetchone())
        else:
            # PostgreSQL: INSERT ... ON CONFLICT UPDATE
            query = """INSERT INTO weekly_plans (user_id, week_start, focus, plan_json)
                      VALUES (%s, %s, %s, %s)
                      ON CONFLICT (user_id, week_start)
                      DO UPDATE SET focus = EXCLUDED.focus, plan_json = EXCLUDED.plan_json
                      RETURNING *"""
            cur.execute(query, (user_id, week_start, plan.focus, json.dumps(plan_json)))
            result = dict_from_row(cur.fetchone())
        
        conn.commit()
        
        # Parse plan_json if needed
        if isinstance(result.get('plan_json'), str):
            result['plan_json'] = json.loads(result['plan_json'])
        
        response = {
            "user_id": result['user_id'],
            "week_start": str(result['week_start']),
            "focus": result.get('focus', 'hybrid'),
            "days": result.get('plan_json', {}).get('days', [])
        }
        log.info("weekly_plan_saved", extra={"user_id": user_id, "week_start": response["week_start"], "days": len(response["days"])})
        metrics.record_domain_event("weekly_plan_saved")
        return response

@router.delete("/{user_id}")
def delete_weekly_plan(user_id: str, week_start: str, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    """Delete a specific weekly plan"""
    with get_db() as conn:
        cur = get_cursor(conn)
        placeholder = "?" if USE_SQLITE else "%s"
        cur.execute(
            f"DELETE FROM weekly_plans WHERE user_id = {placeholder} AND week_start = {placeholder}",
            (user_id, week_start)
        )
        conn.commit()
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Weekly plan not found")
        
        log.info("weekly_plan_deleted", extra={"user_id": user_id, "week_start": week_start})
        metrics.record_domain_event("weekly_plan_deleted")
        return {"message": "Weekly plan deleted"}
