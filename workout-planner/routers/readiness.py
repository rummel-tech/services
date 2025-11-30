from fastapi import APIRouter, HTTPException, Request
import metrics
from database import get_db, get_cursor, USE_SQLITE
from datetime import datetime, timedelta
from slowapi import Limiter
from slowapi.util import get_remote_address
from cache import cache_response

router = APIRouter(prefix="/readiness", tags=["readiness"])
limiter = Limiter(key_func=get_remote_address)

def _query(conn, sql, params):
    cur = get_cursor(conn)
    if USE_SQLITE:
        sql = sql.replace('%s', '?')
    cur.execute(sql, params)
    return cur.fetchall()

def _avg(values):
    return sum(values)/len(values) if values else None

@cache_response("readiness", ttl_seconds=300)  # Cache for 5 minutes
def _calculate_readiness(user_id: str) -> dict:
    """Calculate readiness score with expensive database queries and computations."""
    now = datetime.utcnow()
    day_window_start = (now - timedelta(days=1)).isoformat(timespec='seconds')
    baseline_window_start = (now - timedelta(days=14)).isoformat(timespec='seconds')
    with get_db() as conn:
        # Fetch last day samples
        hrvs = _query(conn, "SELECT value FROM health_samples WHERE user_id = %s AND sample_type = 'hrv' AND start_time >= %s", (user_id, day_window_start))
        rests = _query(conn, "SELECT value FROM health_samples WHERE user_id = %s AND sample_type = 'resting_hr' AND start_time >= %s", (user_id, day_window_start))
        sleeps = _query(conn, "SELECT (julianday(end_time) - julianday(start_time))*24.0 AS hours FROM health_samples WHERE user_id = %s AND sample_type = 'sleep_stage' AND start_time >= %s", (user_id, day_window_start))
        # Baselines (14 days)
        hrv_baseline = _query(conn, "SELECT value FROM health_samples WHERE user_id = %s AND sample_type = 'hrv' AND start_time >= %s", (user_id, baseline_window_start))
        resting_baseline = _query(conn, "SELECT value FROM health_samples WHERE user_id = %s AND sample_type = 'resting_hr' AND start_time >= %s", (user_id, baseline_window_start))
    hrv_values = [r['value'] if isinstance(r, dict) else r[0] for r in hrvs]
    resting_values = [r['value'] if isinstance(r, dict) else r[0] for r in rests]
    sleep_hours = [r['hours'] if isinstance(r, dict) else r[0] for r in sleeps]
    hrv_baseline_vals = [r['value'] if isinstance(r, dict) else r[0] for r in hrv_baseline]
    resting_baseline_vals = [r['value'] if isinstance(r, dict) else r[0] for r in resting_baseline]

    avg_hrv = _avg(hrv_values)
    avg_resting = _avg(resting_values)
    total_sleep = sum(sleep_hours) if sleep_hours else None
    baseline_hrv = _avg(hrv_baseline_vals)
    baseline_resting = _avg(resting_baseline_vals)

    # Normalize components to 0..1
    def norm_hrv(val, base):
        if val is None or base is None:
            return 0.5
        return max(0.0, min(1.0, val / base))
    def norm_resting(val, base):
        if val is None or base is None:
            return 0.5
        # Lower resting HR better: invert ratio
        ratio = base / val if val != 0 else 0
        return max(0.0, min(1.0, ratio))
    def norm_sleep(hours):
        if hours is None:
            return 0.5
        return max(0.0, min(1.0, hours / 8.0))

    hrv_score = norm_hrv(avg_hrv, baseline_hrv)
    resting_score = norm_resting(avg_resting, baseline_resting)
    sleep_score = norm_sleep(total_sleep)
    readiness_score = round((hrv_score * 0.4 + resting_score * 0.3 + sleep_score * 0.3), 3)
    metrics.record_domain_event("readiness_computed")

    return {
        "user_id": user_id,
        "hrv": avg_hrv,
        "hrv_baseline": baseline_hrv,
        "resting_hr": avg_resting,
        "resting_hr_baseline": baseline_resting,
        "sleep_hours": total_sleep,
        "scores": {
            "hrv": hrv_score,
            "resting_hr": resting_score,
            "sleep": sleep_score,
        },
        "readiness": readiness_score,
        "window": {
            "day_start": day_window_start,
            "baseline_start": baseline_window_start,
        }
    }

@router.get("")
@limiter.limit("60/minute")
def readiness(request: Request, user_id: str):
    """Get readiness score for user (cached for 5 minutes)."""
    return _calculate_readiness(user_id)