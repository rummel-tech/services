from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.database import get_db, get_cursor, USE_SQLITE

router = APIRouter(prefix="/swim", tags=["swim"])

class SwimMetricsCreate(BaseModel):
    user_id: str
    date: str
    distance_meters: float
    duration_seconds: int
    avg_pace_seconds: float
    water_type: str = 'pool'
    stroke_rate: Optional[float] = None

@router.get("")
def get_swim_metrics(user_id: str, limit: int = 30):
    """Get recent swim metrics for a user"""
    with get_db() as conn:
        cur = get_cursor(conn)
        placeholder = "?" if USE_SQLITE else "%s"
        cur.execute(
            f"""SELECT * FROM swim_metrics
               WHERE user_id = {placeholder}
               ORDER BY date DESC
               LIMIT {placeholder}""",
            (user_id, limit)
        )
        rows = cur.fetchall()
        if USE_SQLITE:
            rows = [dict(r) for r in rows]
        return rows

@router.post("")
def create_swim_metrics(metrics: SwimMetricsCreate):
    """Log a swim workout"""
    with get_db() as conn:
        cur = get_cursor(conn)
        placeholder = "?" if USE_SQLITE else "%s"
        if USE_SQLITE:
            cur.execute(
                f"""INSERT INTO swim_metrics
                   (user_id, date, distance_meters, duration_seconds, avg_pace_seconds, water_type, stroke_rate)
                   VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})""",
                (metrics.user_id, metrics.date, metrics.distance_meters,
                 metrics.duration_seconds, metrics.avg_pace_seconds, metrics.water_type, metrics.stroke_rate)
            )
            cur.execute(f"SELECT * FROM swim_metrics WHERE id = last_insert_rowid()")
            row = cur.fetchone()
            row = dict(row) if row else None
        else:
            cur.execute(
                """INSERT INTO swim_metrics
                   (user_id, date, distance_meters, duration_seconds, avg_pace_seconds, water_type, stroke_rate)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING *""",
                (metrics.user_id, metrics.date, metrics.distance_meters,
                 metrics.duration_seconds, metrics.avg_pace_seconds, metrics.water_type, metrics.stroke_rate)
            )
            row = cur.fetchone()
        return row

@router.get("/trends")
def get_swim_trends(user_id: str, days: int = 90):
    """Get swim performance trends over time"""
    with get_db() as conn:
        cur = get_cursor(conn)
        placeholder = "?" if USE_SQLITE else "%s"
        if USE_SQLITE:
            cur.execute(
                f"""SELECT
                     date,
                     SUM(distance_meters) as total_distance,
                     AVG(avg_pace_seconds) as avg_pace,
                     AVG(stroke_rate) as avg_stroke_rate,
                     COUNT(*) as swim_count
                   FROM swim_metrics
                   WHERE user_id = {placeholder}
                     AND date >= date('now', '-' || {placeholder} || ' days')
                   GROUP BY date
                   ORDER BY date ASC""",
                (user_id, days)
            )
        else:
            cur.execute(
                """SELECT
                     date,
                     SUM(distance_meters) as total_distance,
                     AVG(avg_pace_seconds) as avg_pace,
                     AVG(stroke_rate) as avg_stroke_rate,
                     COUNT(*) as swim_count
                   FROM swim_metrics
                   WHERE user_id = %s
                     AND date >= CURRENT_DATE - %s
                   GROUP BY date
                   ORDER BY date ASC""",
                (user_id, days)
            )
        rows = cur.fetchall()
        if USE_SQLITE:
            rows = [dict(r) for r in rows]
        return rows

@router.delete("/{metric_id}")
def delete_swim_metrics(metric_id: int):
    """Delete a swim metrics entry"""
    with get_db() as conn:
        cur = get_cursor(conn)
        placeholder = "?" if USE_SQLITE else "%s"
        if USE_SQLITE:
            cur.execute(f"DELETE FROM swim_metrics WHERE id = {placeholder}", (metric_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Swim metrics not found")
        else:
            cur.execute(f"DELETE FROM swim_metrics WHERE id = {placeholder} RETURNING id", (metric_id,))
            deleted = cur.fetchone()
            if not deleted:
                raise HTTPException(status_code=404, detail="Swim metrics not found")
        return {"deleted": metric_id}
