from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List, Optional
from database import get_db, get_cursor, USE_SQLITE
from logging_config import get_logger
import metrics
from auth_service import TokenData
from routers.auth import get_current_user
from cache import cache_response, invalidate_user_cache

log = get_logger("api.health")

router = APIRouter(prefix="/health", tags=["health"])

class HealthSample(BaseModel):
    user_id: str
    sample_type: str
    value: Optional[float] = None
    unit: Optional[str] = None
    start_time: Optional[str] = None  # ISO8601
    end_time: Optional[str] = None    # ISO8601
    source_app: Optional[str] = None
    source_uuid: Optional[str] = None

class BulkSamples(BaseModel):
    samples: List[HealthSample]

@router.post("/samples")
def ingest_samples(payload: BulkSamples, current_user: TokenData = Depends(get_current_user)):
    if not payload.samples:
        log.warning("health_ingest_empty")
        raise HTTPException(status_code=400, detail="No samples provided")
    if payload.samples and current_user.user_id != payload.samples[0].user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    with get_db() as conn:
        cur = get_cursor(conn)
        placeholder = "?" if USE_SQLITE else "%s"
        values_clause = []
        params = []
        for s in payload.samples:
            values_clause.append(f"({placeholder},{placeholder},{placeholder},{placeholder},{placeholder},{placeholder},{placeholder},{placeholder})")
            params.extend([
                s.user_id,
                s.sample_type,
                s.value,
                s.unit,
                s.start_time,
                s.end_time,
                s.source_app,
                s.source_uuid,
            ])
        base = "INSERT INTO health_samples (user_id, sample_type, value, unit, start_time, end_time, source_app, source_uuid) VALUES "
        query = base + ",".join(values_clause)
        if USE_SQLITE:
            query = "INSERT OR IGNORE " + query[len("INSERT "):]  # Convert to INSERT OR IGNORE for dedup
            # SQLite doesn't properly report rowcount with OR IGNORE, so count manually
            cur.execute("SELECT COUNT(*) as cnt FROM health_samples WHERE user_id = ?", (payload.samples[0].user_id,))
            before_count = cur.fetchone()[0] if USE_SQLITE else cur.fetchone()['cnt']
            cur.execute(query, params)
            cur.execute("SELECT COUNT(*) as cnt FROM health_samples WHERE user_id = ?", (payload.samples[0].user_id,))
            after_count = cur.fetchone()[0] if USE_SQLITE else cur.fetchone()['cnt']
            inserted_count = after_count - before_count
        else:
            cur.execute(query, params)
            inserted_count = cur.rowcount
    log.info("health_samples_ingested", extra={"inserted": inserted_count, "total": len(payload.samples), "user_id": payload.samples[0].user_id if payload.samples else None})
    metrics.record_domain_event("health_samples_ingested")

    # Invalidate all health-related caches for this user
    if payload.samples and inserted_count > 0:
        invalidate_user_cache(payload.samples[0].user_id)
        log.debug("cache_invalidated_after_ingest", extra={"user_id": payload.samples[0].user_id})

    return {"inserted": inserted_count, "total": len(payload.samples)}

@router.get("/samples")
def list_samples(user_id: str, sample_type: Optional[str] = None, limit: int = 100, current_user: TokenData = Depends(get_current_user)):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    with get_db() as conn:
        cur = get_cursor(conn)
        base = "SELECT * FROM health_samples WHERE user_id = %s" if not USE_SQLITE else "SELECT * FROM health_samples WHERE user_id = ?"
        params = [user_id]
        if sample_type:
            base += " AND sample_type = %s" if not USE_SQLITE else " AND sample_type = ?"
            params.append(sample_type)
        base += " ORDER BY start_time DESC LIMIT %s" if not USE_SQLITE else " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)
        cur.execute(base, tuple(params))
        rows = cur.fetchall()
        if USE_SQLITE:
            result = [dict(r) for r in rows]
        else:
            result = rows
        log.info("health_samples_list", extra={"user_id": user_id, "sample_type": sample_type, "count": len(result)})
        metrics.record_domain_event("health_samples_list")
        return result

@cache_response("health_summary", ttl_seconds=300)  # Cache for 5 minutes
def _calculate_summary(user_id: str, days: int = 7) -> dict:
    """Calculate health summary with expensive aggregation query."""
    with get_db() as conn:
        cur = get_cursor(conn)
        placeholder = "?" if USE_SQLITE else "%s"
        # Compute since timestamp (assumes start_time stored as ISO8601 date or datetime string)
        # For SQLite simple string comparison works if ISO8601 format used.
        from datetime import datetime, timedelta
        since = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec='seconds')
        query = f"SELECT sample_type, COUNT(*) as count, SUM(value) as total, AVG(value) as avg_value FROM health_samples WHERE user_id = {placeholder} AND start_time >= {placeholder} GROUP BY sample_type"
        cur.execute(query, (user_id, since))
        rows = cur.fetchall()
        def row_to_dict(r):
            return dict(r) if USE_SQLITE else dict(r)
        result = {}
        for r in rows:
            d = row_to_dict(r)
            st = d.get('sample_type')
            if st:
                result[st] = d
        log.info("health_summary", extra={"user_id": user_id, "types": list(result.keys())})
        metrics.record_domain_event("health_summary")
        return result

@router.get("/summary")
def summary(user_id: str, days: int = 7):
    """Get health summary (cached for 5 minutes)."""
    return _calculate_summary(user_id, days)
# Old health metrics router - keeping endpoints but using shared router above

class HealthMetricsCreate(BaseModel):
    user_id: str
    date: str
    hrv_ms: Optional[float] = None
    resting_hr: Optional[int] = None
    vo2max: Optional[float] = None
    sleep_hours: Optional[float] = None
    weight_kg: Optional[float] = None
    rpe: Optional[int] = None
    soreness: Optional[int] = None
    mood: Optional[int] = None

class HealthMetricsUpdate(BaseModel):
    hrv_ms: Optional[float] = None
    resting_hr: Optional[int] = None
    vo2max: Optional[float] = None
    sleep_hours: Optional[float] = None
    weight_kg: Optional[float] = None
    rpe: Optional[int] = None
    soreness: Optional[int] = None
    mood: Optional[int] = None

@router.get("/metrics")
def get_health_metrics(user_id: str, limit: int = 30):
    """Get recent health metrics for a user"""
    with get_db() as conn:
        cur = get_cursor(conn)
        placeholder = "?" if USE_SQLITE else "%s"
        cur.execute(
            f"""SELECT * FROM health_metrics
               WHERE user_id = {placeholder}
               ORDER BY date DESC
               LIMIT {placeholder}""",
            (user_id, limit)
        )
        return cur.fetchall()

@router.get("/date/{metric_date}")
def get_health_metrics_by_date(user_id: str, metric_date: str):
    """Get health metrics for a specific date"""
    with get_db() as conn:
        cur = get_cursor(conn)
        placeholder = "?" if USE_SQLITE else "%s"
        cur.execute(
            f"SELECT * FROM health_metrics WHERE user_id = {placeholder} AND date = {placeholder}",
            (user_id, metric_date)
        )
        metric = cur.fetchone()
        if not metric:
            raise HTTPException(status_code=404, detail="No metrics found for this date")
        return metric

@router.post("")
def create_health_metrics(metrics: HealthMetricsCreate):
    """Create or update health metrics for a date"""
    with get_db() as conn:
        cur = get_cursor(conn)
        placeholder = "?" if USE_SQLITE else "%s"
        if USE_SQLITE:
            # SQLite: Use INSERT OR REPLACE
            cur.execute(
                f"""INSERT OR REPLACE INTO health_metrics
                   (user_id, date, hrv_ms, resting_hr, vo2max, sleep_hours, weight_kg, rpe, soreness, mood)
                   VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})""",
                (metrics.user_id, metrics.date, metrics.hrv_ms, metrics.resting_hr,
                 metrics.vo2max, metrics.sleep_hours, metrics.weight_kg,
                 metrics.rpe, metrics.soreness, metrics.mood)
            )
            # Fetch the inserted/updated row
            cur.execute(
                f"SELECT * FROM health_metrics WHERE user_id = {placeholder} AND date = {placeholder}",
                (metrics.user_id, metrics.date)
            )
            row = cur.fetchone()
        else:
            # PostgreSQL: Use ON CONFLICT with RETURNING
            cur.execute(
                """INSERT INTO health_metrics
                   (user_id, date, hrv_ms, resting_hr, vo2max, sleep_hours, weight_kg, rpe, soreness, mood)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, date)
                   DO UPDATE SET
                     hrv_ms = EXCLUDED.hrv_ms,
                     resting_hr = EXCLUDED.resting_hr,
                     vo2max = EXCLUDED.vo2max,
                     sleep_hours = EXCLUDED.sleep_hours,
                     weight_kg = EXCLUDED.weight_kg,
                     rpe = EXCLUDED.rpe,
                     soreness = EXCLUDED.soreness,
                     mood = EXCLUDED.mood
                   RETURNING *""",
                (metrics.user_id, metrics.date, metrics.hrv_ms, metrics.resting_hr,
                 metrics.vo2max, metrics.sleep_hours, metrics.weight_kg,
                 metrics.rpe, metrics.soreness, metrics.mood)
            )
            row = cur.fetchone()
        if row:
            log.info("health_metrics_upsert", extra={"user_id": metrics.user_id, "date": metrics.date})
            metrics.record_domain_event("health_metrics_upsert")
        return row

@router.put("/{metric_id}")
def update_health_metrics(metric_id: int, metrics: HealthMetricsUpdate):
    """Update specific health metrics"""
    updates = {k: v for k, v in metrics.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    placeholder = "?" if USE_SQLITE else "%s"
    set_clause = ", ".join([f"{k} = {placeholder}" for k in updates.keys()])
    values = list(updates.values()) + [metric_id]

    with get_db() as conn:
        cur = get_cursor(conn)
        if USE_SQLITE:
            cur.execute(
                f"UPDATE health_metrics SET {set_clause} WHERE id = {placeholder}",
                values
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Health metrics not found")
            # Fetch the updated row
            cur.execute(f"SELECT * FROM health_metrics WHERE id = {placeholder}", (metric_id,))
            updated = cur.fetchone()
        else:
            cur.execute(
                f"UPDATE health_metrics SET {set_clause} WHERE id = {placeholder} RETURNING *",
                values
            )
            updated = cur.fetchone()
            if not updated:
                raise HTTPException(status_code=404, detail="Health metrics not found")
        log.info("health_metrics_updated", extra={"metric_id": metric_id, "fields": list(updates.keys())})
        metrics.record_domain_event("health_metrics_updated")
        return updated

@router.delete("/{metric_id}")
def delete_health_metrics(metric_id: int):
    """Delete health metrics entry"""
    with get_db() as conn:
        cur = get_cursor(conn)
        placeholder = "?" if USE_SQLITE else "%s"
        if USE_SQLITE:
            cur.execute(f"DELETE FROM health_metrics WHERE id = {placeholder}", (metric_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Health metrics not found")
        else:
            cur.execute(f"DELETE FROM health_metrics WHERE id = {placeholder} RETURNING id", (metric_id,))
            deleted = cur.fetchone()
            if not deleted:
                raise HTTPException(status_code=404, detail="Health metrics not found")
        log.info("health_metrics_deleted", extra={"metric_id": metric_id})
        metrics.record_domain_event("health_metrics_deleted")
        return {"deleted": metric_id}

@cache_response("health_trends", ttl_seconds=600)  # Cache for 10 minutes
def _calculate_health_trends(user_id: str, days: int = 30) -> dict:
    """Calculate health trends with expensive time-series aggregation."""
    with get_db() as conn:
        cur = get_cursor(conn)
        placeholder = "?" if USE_SQLITE else "%s"
        if USE_SQLITE:
            # SQLite: Use date() function for date arithmetic
            cur.execute(
                f"""SELECT
                     date,
                     hrv_ms,
                     resting_hr,
                     sleep_hours,
                     weight_kg,
                     rpe,
                     soreness,
                     mood
                   FROM health_metrics
                   WHERE user_id = {placeholder}
                     AND date >= date('now', '-' || {placeholder} || ' days')
                   ORDER BY date ASC""",
                (user_id, days)
            )
        else:
            # PostgreSQL: Use CURRENT_DATE
            cur.execute(
                """SELECT
                     date,
                     hrv_ms,
                     resting_hr,
                     sleep_hours,
                     weight_kg,
                     rpe,
                     soreness,
                     mood
                   FROM health_metrics
                   WHERE user_id = %s
                     AND date >= CURRENT_DATE - %s
                   ORDER BY date ASC""",
                (user_id, days)
            )
        data = cur.fetchall()
        
        # Calculate averages
        if data:
            avg_hrv = sum(d['hrv_ms'] for d in data if d.get('hrv_ms')) / len([d for d in data if d.get('hrv_ms')]) if any(d.get('hrv_ms') for d in data) else None
            avg_hr = sum(d['resting_hr'] for d in data if d.get('resting_hr')) / len([d for d in data if d.get('resting_hr')]) if any(d.get('resting_hr') for d in data) else None
            avg_sleep = sum(d['sleep_hours'] for d in data if d.get('sleep_hours')) / len([d for d in data if d.get('sleep_hours')]) if any(d.get('sleep_hours') for d in data) else None
            
            response = {
                "data": data,
                "averages": {
                    "hrv_ms": round(avg_hrv, 1) if avg_hrv else None,
                    "resting_hr": round(avg_hr, 1) if avg_hr else None,
                    "sleep_hours": round(avg_sleep, 1) if avg_sleep else None,
                },
                "days": days
            }
            log.info("health_trends", extra={"user_id": user_id, "days": days, "count": len(data)})
            metrics.record_domain_event("health_trends")
            return response
        log.info("health_trends_empty", extra={"user_id": user_id, "days": days})
        metrics.record_domain_event("health_trends_empty")
        return {"data": [], "averages": {}, "days": days}

@router.get("/trends")
def get_health_trends(user_id: str, days: int = 30):
    """Get health metrics trends over time (cached for 10 minutes)."""
    return _calculate_health_trends(user_id, days)
