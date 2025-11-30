from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_db, get_cursor

router = APIRouter(prefix="/swim", tags=["swim"])

class SwimMetricsCreate(BaseModel):
    user_id: str
    workout_id: Optional[int] = None
    distance_meters: float
    avg_pace_seconds: float
    stroke_rate: Optional[float] = None
    water_type: str = 'pool'

@router.get("")
def get_swim_metrics(user_id: str, limit: int = 30):
    """Get recent swim metrics for a user"""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """SELECT * FROM swim_metrics 
               WHERE user_id = %s 
               ORDER BY created_at DESC 
               LIMIT %s""",
            (user_id, limit)
        )
        return cur.fetchall()

@router.post("")
def create_swim_metrics(metrics: SwimMetricsCreate):
    """Log a swim workout"""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """INSERT INTO swim_metrics 
               (user_id, workout_id, distance_meters, avg_pace_seconds, stroke_rate, water_type)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING *""",
            (metrics.user_id, metrics.workout_id, metrics.distance_meters, 
             metrics.avg_pace_seconds, metrics.stroke_rate, metrics.water_type)
        )
        return cur.fetchone()

@router.get("/trends")
def get_swim_trends(user_id: str, days: int = 90):
    """Get swim performance trends over time"""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """SELECT 
                 DATE(created_at) as date,
                 SUM(distance_meters) as total_distance,
                 AVG(avg_pace_seconds) as avg_pace,
                 AVG(stroke_rate) as avg_stroke_rate,
                 COUNT(*) as swim_count
               FROM swim_metrics 
               WHERE user_id = %s 
                 AND created_at >= NOW() - INTERVAL '%s days'
               GROUP BY DATE(created_at)
               ORDER BY date ASC""",
            (user_id, days)
        )
        return cur.fetchall()

@router.delete("/{metric_id}")
def delete_swim_metrics(metric_id: int):
    """Delete a swim metrics entry"""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("DELETE FROM swim_metrics WHERE id = %s RETURNING id", (metric_id,))
        deleted = cur.fetchone()
        if not deleted:
            raise HTTPException(status_code=404, detail="Swim metrics not found")
        return {"deleted": metric_id}
