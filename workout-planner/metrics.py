"""
Metrics shim for Workout Planner.

Delegates to the common library's metrics implementation with fallback.
"""

import sys
from pathlib import Path

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
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
    )

    # For backward compatibility with code that references REQUESTS_IN_PROGRESS directly
    from common.metrics import _get_metrics
    _m = _get_metrics()
    REQUESTS_IN_PROGRESS = _m["requests_in_progress"] if _m else None

except ImportError:
    # Fallback when prometheus not installed
    import time

    class _NoopCounter:
        def labels(self, **kwargs):
            return self
        def inc(self, amount=1.0):
            pass
        def dec(self, amount=1.0):
            pass
        def observe(self, value):
            pass

    REQUESTS_IN_PROGRESS = _NoopCounter()

    def init_metrics(prefix="service"):
        pass

    def start_timer():
        return time.time()

    def observe_request(method, path, status_code, start_time):
        pass

    def inc_requests_in_progress(method, path):
        pass

    def dec_requests_in_progress(method, path):
        pass

    def record_error(error_type):
        pass

    def record_domain_event(event):
        pass

    def record_cache_operation(operation):
        pass

    def record_db_operation(operation, table, latency_seconds=None):
        pass

    def record_redis_operation(operation, success):
        pass

    def metrics_response():
        return b"# Metrics not available\n", "text/plain"
