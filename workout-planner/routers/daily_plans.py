from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
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

class DailyPlanData(BaseModel):
    user_id: str
    date: str  # ISO date format
    plan_json: dict  # {warmup: [], main: [], cooldown: [], notes: str}
    status: Optional[str] = "pending"  # pending, complete, skipped
    ai_notes: Optional[str] = None

@router.get("/{user_id}/{plan_date}")
def get_daily_plan(user_id: str, plan_date: str, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    """Get user's daily plan for specified date"""
    with get_db() as conn:
        cur = get_cursor(conn)
        
        query, params = adapt_query(
            "SELECT * FROM daily_plans WHERE user_id = %s AND date = %s",
            (user_id, plan_date)
        )
        
        cur.execute(query, params)
        row = cur.fetchone()
        
        if not row:
            # Return default empty plan (flattened fields)
            result = {
                "user_id": user_id,
                "date": plan_date,
                "warmup": [],
                "main": [],
                "cooldown": [],
                "notes": "",
                "status": "pending",
                "ai_notes": None
            }
            log.info("daily_plan_default", extra={"user_id": user_id, "date": plan_date})
            metrics.record_domain_event("daily_plan_default")
            return result
        
        result = dict_from_row(row)
        
        # Parse plan_json if it's a string (SQLite stores JSON as text)
        if isinstance(result.get('plan_json'), str):
            result['plan_json'] = json.loads(result['plan_json'])
        
        # Return the plan data
        response = {
            "user_id": result['user_id'],
            "date": str(result['date']),
            "warmup": result['plan_json'].get('warmup', []),
            "main": result['plan_json'].get('main', []),
            "cooldown": result['plan_json'].get('cooldown', []),
            "notes": result['plan_json'].get('notes', ''),
            "status": result.get('status', 'pending'),
            "ai_notes": result.get('ai_notes')
        }
        log.info("daily_plan_retrieved", extra={"user_id": user_id, "date": plan_date, "items_main": len(response["main"])})
        metrics.record_domain_event("daily_plan_retrieved")
        return response

@router.put("/{user_id}/{plan_date}")
def update_daily_plan(user_id: str, plan_date: str, plan: DailyPlanData, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    """Create or update user's daily plan"""
    with get_db() as conn:
        cur = get_cursor(conn)
        
        # Convert plan_json to JSON string for storage
        plan_json_str = json.dumps(plan.plan_json)
        
        if USE_SQLITE:
            # SQLite upsert
            query = """
                INSERT INTO daily_plans (user_id, date, plan_json, status, ai_notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, date) 
                DO UPDATE SET 
                    plan_json = excluded.plan_json,
                    status = excluded.status,
                    ai_notes = excluded.ai_notes
            """
            params = (user_id, plan_date, plan_json_str, plan.status, plan.ai_notes)
        else:
            # PostgreSQL upsert
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
            params = (user_id, plan_date, plan_json_str, plan.status, plan.ai_notes)
        
        cur.execute(query, params)
        conn.commit()
        
        # Return the saved plan
        response = {
            "user_id": user_id,
            "date": plan_date,
            "warmup": plan.plan_json.get('warmup', []),
            "main": plan.plan_json.get('main', []),
            "cooldown": plan.plan_json.get('cooldown', []),
            "notes": plan.plan_json.get('notes', ''),
            "status": plan.status,
            "ai_notes": plan.ai_notes,
            "message": "Daily plan saved successfully"
        }
        log.info("daily_plan_saved", extra={"user_id": user_id, "date": plan_date, "warmup": len(response["warmup"]), "main": len(response["main"])})
        metrics.record_domain_event("daily_plan_saved")
        return response

@router.delete("/{user_id}/{plan_date}")
def delete_daily_plan(user_id: str, plan_date: str, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    """Delete user's daily plan"""
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
