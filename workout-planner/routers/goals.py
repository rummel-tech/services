from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from database import get_db, get_cursor, USE_SQLITE
from logging_config import get_logger
import metrics
from auth_service import TokenData
from routers.auth import get_current_user

log = get_logger("api.goals")

router = APIRouter(prefix="/goals", tags=["goals"])

def adapt_query(query: str, params: tuple):
    """Adapt PostgreSQL query to SQLite if needed"""
    if USE_SQLITE:
        # Replace %s with ? for SQLite
        query = query.replace("%s", "?")
        # Replace RETURNING * with separate SELECT (SQLite doesn't support RETURNING before 3.35)
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

class GoalCreate(BaseModel):
    user_id: str
    goal_type: str
    target_value: Optional[float] = None
    target_unit: Optional[str] = None
    target_date: Optional[str] = None
    notes: Optional[str] = None

class GoalUpdate(BaseModel):
    goal_type: Optional[str] = None
    target_value: Optional[float] = None
    target_unit: Optional[str] = None
    target_date: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None

class PlanCreate(BaseModel):
    goal_id: int
    user_id: str
    name: str
    description: Optional[str] = None
    status: Optional[str] = 'active'

class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

@router.get("")
def get_goals(user_id: str, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    with get_db() as conn:
        cur = get_cursor(conn)
        query, params = adapt_query(
            "SELECT * FROM user_goals WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        )
        cur.execute(query, params)
        rows = [dict_from_row(row) for row in cur.fetchall()]
        log.info("goals_list", extra={"user_id": user_id, "count": len(rows)})
        metrics.record_domain_event("goals_list")
        return rows

@router.post("")
def create_goal(goal: GoalCreate, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != goal.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    log.info("goal_create_attempt", extra={"user_id": goal.user_id, "goal_type": goal.goal_type})
    metrics.record_domain_event("goal_create_attempt")
    with get_db() as conn:
        cur = get_cursor(conn)
        query, params = adapt_query(
                """INSERT INTO user_goals (user_id, goal_type, target_value, target_unit, target_date, notes)
                    VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
                (goal.user_id, goal.goal_type, goal.target_value, goal.target_unit, goal.target_date, goal.notes)
        )
        cur.execute(query, params)
        
        if USE_SQLITE:
            # Get the last inserted row
            cur.execute("SELECT * FROM user_goals WHERE id = ?", (cur.lastrowid,))
            created = dict_from_row(cur.fetchone())
        else:
            created = dict_from_row(cur.fetchone())
    if created:
        log.info("goal_created", extra={"user_id": created.get("user_id"), "goal_id": created.get("id"), "goal_type": created.get("goal_type")})
        metrics.record_domain_event("goal_created")
    return created

@router.get("/{goal_id}")
def get_goal(goal_id: int):
    with get_db() as conn:
        cur = get_cursor(conn)
        query, params = adapt_query("SELECT * FROM user_goals WHERE id = %s", (goal_id,))
        cur.execute(query, params)
        goal = cur.fetchone()
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")
        result = dict_from_row(goal)
        log.info("goal_retrieved", extra={"goal_id": goal_id})
        metrics.record_domain_event("goal_retrieved")
        return result

@router.put("/{goal_id}")
def update_goal(goal_id: int, goal: GoalUpdate):
    updates = {k: v for k, v in goal.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    placeholder = "?" if USE_SQLITE else "%s"
    set_clause = ", ".join([f"{k} = {placeholder}" for k in updates.keys()])
    values = list(updates.values()) + [goal_id]
    with get_db() as conn:
        cur = get_cursor(conn)
        if USE_SQLITE:
            cur.execute(f"UPDATE user_goals SET {set_clause} WHERE id = {placeholder}", values)
            cur.execute("SELECT * FROM user_goals WHERE id = ?", (goal_id,))
            updated = cur.fetchone()
        else:
            cur.execute(f"UPDATE user_goals SET {set_clause} WHERE id = {placeholder} RETURNING *", values)
            updated = cur.fetchone()
        if not updated:
            raise HTTPException(status_code=404, detail="Goal not found")
        result = dict_from_row(updated)
        log.info("goal_updated", extra={"goal_id": goal_id, "fields": list(updates.keys())})
        metrics.record_domain_event("goal_updated")
        return result

@router.delete("/{goal_id}")
def delete_goal(goal_id: int):
    with get_db() as conn:
        cur = get_cursor(conn)
        query, params = adapt_query(
            "UPDATE user_goals SET is_active = %s WHERE id = %s",
            (False, goal_id)
        )
        cur.execute(query, params)
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Goal not found")
        log.info("goal_deleted", extra={"goal_id": goal_id})
        metrics.record_domain_event("goal_deleted")
        return {"deleted": goal_id}

@router.get("/{goal_id}/plans")
def get_goal_plans(goal_id: int, user_id: Optional[str] = None):
    with get_db() as conn:
        cur = get_cursor(conn)
        if user_id:
            query, params = adapt_query(
                "SELECT * FROM goal_plans WHERE goal_id = %s AND user_id = %s ORDER BY created_at DESC",
                (goal_id, user_id)
            )
        else:
            query, params = adapt_query(
                "SELECT * FROM goal_plans WHERE goal_id = %s ORDER BY created_at DESC",
                (goal_id,)
            )
        cur.execute(query, params)
        rows = [dict_from_row(row) for row in cur.fetchall()]
        metrics.record_domain_event("goal_plans_list")
        return rows

@router.post("/plans")
def create_goal_plan(plan: PlanCreate):
    with get_db() as conn:
        cur = get_cursor(conn)
        query, params = adapt_query(
            """INSERT INTO goal_plans (goal_id, user_id, name, description, status)
               VALUES (%s, %s, %s, %s, %s) RETURNING *""",
            (plan.goal_id, plan.user_id, plan.name, plan.description, plan.status)
        )
        cur.execute(query, params)
        
        if USE_SQLITE:
            cur.execute("SELECT * FROM goal_plans WHERE id = ?", (cur.lastrowid,))
            created = dict_from_row(cur.fetchone())
        else:
            created = dict_from_row(cur.fetchone())
    if created:
        log.info("goal_plan_created", extra={"plan_id": created.get("id"), "goal_id": created.get("goal_id"), "user_id": created.get("user_id")})
        metrics.record_domain_event("goal_plan_created")
    return created

@router.put("/plans/{plan_id}")
def update_plan(plan_id: int, plan: PlanUpdate):
    updates = {k: v for k, v in plan.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    placeholder = "?" if USE_SQLITE else "%s"
    set_clause = ", ".join([f"{k} = {placeholder}" for k in updates.keys()])
    values = list(updates.values()) + [plan_id]
    
    with get_db() as conn:
        cur = get_cursor(conn)
        query = f"UPDATE goal_plans SET {set_clause} WHERE id = {placeholder}"
        cur.execute(query, values)
        
        if USE_SQLITE:
            cur.execute("SELECT * FROM goal_plans WHERE id = ?", (plan_id,))
            updated = cur.fetchone()
        else:
            query_with_returning = query.replace(f"WHERE id = {placeholder}", f"WHERE id = {placeholder} RETURNING *")
            cur.execute(query_with_returning, values)
            updated = cur.fetchone()
        
        if not updated:
            raise HTTPException(status_code=404, detail="Plan not found")
        result = dict_from_row(updated)
        log.info("goal_plan_updated", extra={"plan_id": plan_id, "fields": list(updates.keys())})
        metrics.record_domain_event("goal_plan_updated")
        return result

@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: int):
    with get_db() as conn:
        cur = get_cursor(conn)
        
        if USE_SQLITE:
            cur.execute("SELECT id FROM goal_plans WHERE id = ?", (plan_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Plan not found")
            cur.execute("DELETE FROM goal_plans WHERE id = ?", (plan_id,))
        else:
            cur.execute("DELETE FROM goal_plans WHERE id = %s RETURNING id", (plan_id,))
            deleted = cur.fetchone()
            if not deleted:
                raise HTTPException(status_code=404, detail="Plan not found")
        
        log.info("goal_plan_deleted", extra={"plan_id": plan_id})
        metrics.record_domain_event("goal_plan_deleted")
        return {"deleted": plan_id}
