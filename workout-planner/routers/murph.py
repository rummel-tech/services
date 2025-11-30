from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_db, get_cursor
import metrics

router = APIRouter(prefix="/murph", tags=["murph"])

class MurphMetricsCreate(BaseModel):
    user_id: str
    workout_id: Optional[int] = None
    run_1_time_seconds: int
    run_2_time_seconds: int
    partition: str  # e.g., "20-10-5" or "singles"
    total_time_seconds: int
    vest_weight: Optional[float] = None
    notes: Optional[str] = None

@router.get("")
def get_murph_metrics(user_id: str, limit: int = 20):
    """Get recent Murph workouts for a user"""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """SELECT * FROM murph_metrics 
               WHERE user_id = %s 
               ORDER BY created_at DESC 
               LIMIT %s""",
            (user_id, limit)
        )
        rows = cur.fetchall()
        metrics.record_domain_event("murph_metrics_list")
        return rows

@router.post("")
def create_murph_metrics(metrics: MurphMetricsCreate):
    """Log a Murph workout"""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """INSERT INTO murph_metrics 
               (user_id, workout_id, run_1_time_seconds, run_2_time_seconds, 
                partition, total_time_seconds, vest_weight, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING *""",
            (metrics.user_id, metrics.workout_id, metrics.run_1_time_seconds, 
             metrics.run_2_time_seconds, metrics.partition, metrics.total_time_seconds, 
             metrics.vest_weight, metrics.notes)
        )
        row = cur.fetchone()
        if row:
            metrics.record_domain_event("murph_metrics_created")
        return row

@router.get("/progress")
def get_murph_progress(user_id: str):
    """Get Murph performance progress over time"""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """SELECT 
                 created_at,
                 total_time_seconds,
                 run_1_time_seconds,
                 run_2_time_seconds,
                 partition,
                 vest_weight,
                 notes
               FROM murph_metrics 
               WHERE user_id = %s 
               ORDER BY created_at ASC""",
            (user_id,)
        )
        data = cur.fetchall()
        
        if data:
            best_time = min(d['total_time_seconds'] for d in data)
            avg_time = sum(d['total_time_seconds'] for d in data) / len(data)
            metrics.record_domain_event("murph_progress")
            return {
                "workouts": data,
                "stats": {
                    "total_murphs": len(data),
                    "best_time_seconds": best_time,
                    "avg_time_seconds": round(avg_time, 1),
                }
            }
        metrics.record_domain_event("murph_progress_empty")
        return {"workouts": [], "stats": {}}

@router.delete("/{metric_id}")
def delete_murph_metrics(metric_id: int):
    """Delete a Murph metrics entry"""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("DELETE FROM murph_metrics WHERE id = %s RETURNING id", (metric_id,))
        deleted = cur.fetchone()
        if not deleted:
            raise HTTPException(status_code=404, detail="Murph metrics not found")
        metrics.record_domain_event("murph_metrics_deleted")
        return {"deleted": metric_id}
