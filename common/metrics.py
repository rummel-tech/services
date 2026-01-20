"""
Prometheus metrics instrumentation for FastAPI services.

Provides counters and histograms for request lifecycle and domain events.
Keep label cardinality low to avoid memory blowups.
"""

from time import time
from typing import Optional

try:
    from prometheus_client import (
        Counter, Summary, Gauge,
        generate_latest, CONTENT_TYPE_LATEST
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


def _create_metrics(prefix: str = "service"):
    """Create metrics with a given prefix."""
    if not PROMETHEUS_AVAILABLE:
        return None

    return {
        "request_count": Counter(
            f"{prefix}_request_total",
            "Total HTTP requests",
            ["method", "path", "status_code"]
        ),
        "requests_in_progress": Gauge(
            f"{prefix}_requests_in_progress",
            "Number of requests in progress",
            ["method", "path"]
        ),
        "request_latency": Summary(
            f"{prefix}_request_latency_seconds",
            "Request latency in seconds",
            ["method", "path"]
        ),
        "domain_event": Counter(
            f"{prefix}_domain_event_total",
            "Domain analytics or business events",
            ["event"]
        ),
        "error_count": Counter(
            f"{prefix}_error_total",
            "Count of error responses",
            ["type"]
        ),
        "cache_operations": Counter(
            f"{prefix}_cache_operations_total",
            "Cache operations (hit/miss/error/invalidated)",
            ["operation"]
        ),
        "db_operations": Counter(
            f"{prefix}_db_operations_total",
            "Database operations",
            ["operation", "table"]
        ),
        "db_latency": Summary(
            f"{prefix}_db_latency_seconds",
            "Database query latency in seconds",
            ["table"]
        ),
        "redis_operations": Counter(
            f"{prefix}_redis_operations_total",
            "Redis operations",
            ["operation", "success"]
        ),
    }


# Default metrics instance (can be overridden by services)
_metrics: Optional[dict] = None
_metrics_prefix: str = "service"


def init_metrics(prefix: str = "service") -> None:
    """
    Initialize metrics with a custom prefix.

    Args:
        prefix: Metric name prefix (e.g., "fitness", "home_manager")
    """
    global _metrics, _metrics_prefix
    _metrics_prefix = prefix
    _metrics = _create_metrics(prefix)


def _get_metrics() -> Optional[dict]:
    """Get or create metrics instance."""
    global _metrics
    if _metrics is None:
        _metrics = _create_metrics(_metrics_prefix)
    return _metrics


def start_timer() -> float:
    """Start a timer for measuring latency."""
    return time()


def observe_request(method: str, path: str, status_code: int, start_time: float) -> None:
    """Record request metrics."""
    metrics = _get_metrics()
    if metrics is None:
        return

    metrics["request_count"].labels(
        method=method, path=path, status_code=str(status_code)
    ).inc()
    metrics["request_latency"].labels(method=method, path=path).observe(
        time() - start_time
    )
    if status_code >= 500:
        metrics["error_count"].labels(type="http_5xx").inc()


def inc_requests_in_progress(method: str, path: str) -> None:
    """Increment in-progress request gauge."""
    metrics = _get_metrics()
    if metrics:
        metrics["requests_in_progress"].labels(method=method, path=path).inc()


def dec_requests_in_progress(method: str, path: str) -> None:
    """Decrement in-progress request gauge."""
    metrics = _get_metrics()
    if metrics:
        metrics["requests_in_progress"].labels(method=method, path=path).dec()


def record_error(error_type: str) -> None:
    """Record an error."""
    metrics = _get_metrics()
    if metrics:
        metrics["error_count"].labels(type=error_type).inc()


def record_domain_event(event: str) -> None:
    """Record a domain/business event."""
    metrics = _get_metrics()
    if metrics:
        metrics["domain_event"].labels(event=event).inc()


def record_cache_operation(operation: str) -> None:
    """Record a cache operation (hit/miss/error/invalidated)."""
    metrics = _get_metrics()
    if metrics:
        metrics["cache_operations"].labels(operation=operation).inc()


def record_db_operation(
    operation: str, table: str, latency_seconds: Optional[float] = None
) -> None:
    """Record a database operation."""
    metrics = _get_metrics()
    if metrics is None:
        return

    metrics["db_operations"].labels(operation=operation, table=table).inc()
    if latency_seconds is not None:
        metrics["db_latency"].labels(table=table).observe(latency_seconds)


def record_redis_operation(operation: str, success: bool) -> None:
    """Record a Redis operation."""
    metrics = _get_metrics()
    if metrics:
        metrics["redis_operations"].labels(
            operation=operation, success=str(success).lower()
        ).inc()


def metrics_response() -> tuple:
    """
    Generate Prometheus metrics response.

    Returns:
        Tuple of (data bytes, content type)
    """
    if not PROMETHEUS_AVAILABLE:
        return b"# Prometheus client not available\n", "text/plain"

    data = generate_latest()
    return data, CONTENT_TYPE_LATEST
