import time
import logging
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi import APIRouter
from common.database import get_connection, get_cursor, adapt_query
from core.database import USE_SQLITE

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/healthz")
async def liveness():
    return {"status": "ok"}


@router.get("/readyz")
async def readiness():
    db_ok, db_latency_ms = await _check_database()
    status = "ok" if db_ok else "degraded"
    return {
        "status": status,
        "checks": {
            "database": {"ok": db_ok, "latency_ms": db_latency_ms},
        },
    }


async def _check_database() -> tuple[bool, float]:
    start = time.monotonic()
    try:
        with get_connection() as conn:
            cur = get_cursor(conn)
            cur.execute(adapt_query("SELECT 1", USE_SQLITE))
        return True, round((time.monotonic() - start) * 1000, 2)
    except Exception as exc:
        logger.warning("DB health check failed: %s", exc)
        return False, round((time.monotonic() - start) * 1000, 2)
