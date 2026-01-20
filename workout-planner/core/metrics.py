"""
Metrics configuration for Workout Planner.

Delegates to the common library's metrics implementation.
"""

import sys
from pathlib import Path

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Re-export everything from common.metrics
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

# Initialize with workout-planner prefix
init_metrics("fitness")

# For backward compatibility, expose commonly used metrics
try:
    from common.metrics import _get_metrics
    _m = _get_metrics()
    if _m:
        REQUEST_COUNT = _m.get("request_count")
        REQUESTS_IN_PROGRESS = _m.get("requests_in_progress")
        REQUEST_LATENCY = _m.get("request_latency")
        DOMAIN_EVENT = _m.get("domain_event")
        ERROR_COUNT = _m.get("error_count")
        CACHE_OPERATIONS = _m.get("cache_operations")
        DB_OPERATIONS = _m.get("db_operations")
        DB_LATENCY = _m.get("db_latency")
        REDIS_OPERATIONS = _m.get("redis_operations")
except Exception:
    pass

__all__ = [
    "init_metrics",
    "start_timer",
    "observe_request",
    "inc_requests_in_progress",
    "dec_requests_in_progress",
    "record_error",
    "record_domain_event",
    "record_cache_operation",
    "record_db_operation",
    "record_redis_operation",
    "metrics_response",
    "PROMETHEUS_AVAILABLE",
]
