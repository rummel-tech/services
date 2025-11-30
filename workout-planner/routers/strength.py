from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_db, get_cursor
import metrics

router = APIRouter(prefix="/strength", tags=["strength"])

class StrengthMetricsCreate(BaseModel):
    user_id: str
    date: str
    lift: str
    weight: float
    reps: int
    set_number: int
    estimated_1rm: Optional[float] = None
    velocity_m_per_s: Optional[float] = None

@router.get("")
def get_strength_metrics(user_id: str, lift: Optional[str] = None, limit: int = 50):
    """Get recent strength metrics for a user"""
    with get_db() as conn:
        cur = get_cursor(conn)
        if lift:
            cur.execute(
                """SELECT * FROM strength_metrics 
                   WHERE user_id = %s AND lift = %s
                   ORDER BY date DESC, set_number DESC 
                   LIMIT %s""",
                (user_id, lift, limit)
            )
        else:
            cur.execute(
                """SELECT * FROM strength_metrics 
                   WHERE user_id = %s 
                   ORDER BY date DESC, set_number DESC 
                   LIMIT %s""",
                (user_id, limit)
            )
        rows = cur.fetchall()
        metrics.record_domain_event("strength_metrics_list")
        return rows

@router.post("")
def create_strength_metrics(payload: StrengthMetricsCreate):
    """Log a strength training set"""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """INSERT INTO strength_metrics 
               (user_id, date, lift, weight, reps, set_number, estimated_1rm, velocity_m_per_s)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id, date, lift, set_number)
               DO UPDATE SET
                 weight = EXCLUDED.weight,
                 reps = EXCLUDED.reps,
                 estimated_1rm = EXCLUDED.estimated_1rm,
                 velocity_m_per_s = EXCLUDED.velocity_m_per_s
               RETURNING *""",
            (payload.user_id, payload.date, payload.lift, payload.weight, 
             payload.reps, payload.set_number, payload.estimated_1rm, payload.velocity_m_per_s)
        )
        row = cur.fetchone()
        if row:
            metrics.record_domain_event("strength_metrics_created")
        return row

@router.get("/progress/{lift}")
def get_lift_progress(user_id: str, lift: str, days: int = 90):
    """Get progress for a specific lift over time"""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """SELECT 
                 date,
                 MAX(estimated_1rm) as max_1rm,
                 MAX(weight) as max_weight,
                 AVG(reps) as avg_reps,
                 COUNT(*) as total_sets
               FROM strength_metrics 
               WHERE user_id = %s 
                 AND lift = %s
                 AND date >= CURRENT_DATE - %s
               GROUP BY date
               ORDER BY date ASC""",
            (user_id, lift, days)
        )
        rows = cur.fetchall()
        metrics.record_domain_event("strength_lift_progress")
        return rows

@router.delete("/{metric_id}")
def delete_strength_metrics(metric_id: int):
    """Delete a strength metrics entry"""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("DELETE FROM strength_metrics WHERE id = %s RETURNING id", (metric_id,))
        deleted = cur.fetchone()
        if not deleted:
            raise HTTPException(status_code=404, detail="Strength metrics not found")
        metrics.record_domain_event("strength_metrics_deleted")
        return {"deleted": metric_id}
