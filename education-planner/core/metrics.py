"""Metrics — delegates to common library."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.metrics import (
    init_metrics,
    start_timer,
    observe_request,
    inc_requests_in_progress,
    dec_requests_in_progress,
    record_error,
    record_domain_event,
    record_cache_operation,
    record_db_operation,
    record_redis_operation,
    metrics_response,
    PROMETHEUS_AVAILABLE,
)

__all__ = [
    'init_metrics',
    'start_timer',
    'observe_request',
    'inc_requests_in_progress',
    'dec_requests_in_progress',
    'record_error',
    'record_domain_event',
    'record_cache_operation',
    'record_db_operation',
    'record_redis_operation',
    'metrics_response',
    'PROMETHEUS_AVAILABLE',
]
