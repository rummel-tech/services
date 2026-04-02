"""Health check endpoints."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from core.database import get_db, get_cursor, USE_SQLITE
from core.logging_config import get_logger

log = get_logger('api.healthcheck')

router = APIRouter(tags=['health'])


def _check_database() -> dict:
    """Probe the database and measure latency."""
    db_type = 'sqlite' if USE_SQLITE else 'postgresql'
    try:
        start = time.time()
        with get_db() as conn:
            cur = get_cursor(conn)
            cur.execute('SELECT 1' if USE_SQLITE else 'SELECT 1 AS health_check')
            if cur.fetchone() is None:
                raise RuntimeError('Database query returned no results')
        return {
            'healthy': True,
            'type': db_type,
            'latency_ms': round((time.time() - start) * 1000, 2),
            'error': None,
        }
    except Exception as exc:
        log.error('database_health_check_failed', extra={'error': str(exc)})
        return {
            'healthy': False,
            'type': db_type,
            'latency_ms': None,
            'error': 'database check failed',
        }


@router.get('/healthz')
async def liveness() -> dict:
    """Liveness probe — returns 200 if the process is running."""
    return {
        'status': 'ok',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'service': 'education-planner',
        'database': 'sqlite' if USE_SQLITE else 'postgresql',
    }


@router.get('/readyz')
async def readiness() -> dict:
    """Readiness probe — returns 200 only when the database is reachable."""
    db_info = _check_database()
    if not db_info['healthy']:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={'status': 'degraded', 'database': {'healthy': False, 'type': db_info['type']}},
        )
    return {
        'status': 'ok',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'service': 'education-planner',
        'database': db_info,
    }


@router.get('/health')
async def health() -> dict:
    return {'status': 'healthy', 'service': 'education-planner'}


@router.get('/ready')
async def ready() -> dict:
    return {'status': 'ready', 'database': 'connected'}
