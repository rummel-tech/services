"""Prometheus metrics instrumentation for the FastAPI backend.

Provides counters and histograms for request lifecycle and domain events.
Keep label cardinality low to avoid memory blowups.
"""
from typing import Optional
from time import time

from prometheus_client import Counter, Summary, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Request metrics
REQUEST_COUNT = Counter(
    "fitness_request_total",
    "Total HTTP requests",
    ["method", "path", "status_code"]
)
REQUESTS_IN_PROGRESS = Gauge(
    "fitness_requests_in_progress",
    "Number of requests in progress",
    ["method", "path"]
)
REQUEST_LATENCY = Summary(
    "fitness_request_latency_seconds",
    "Request latency in seconds",
    ["method", "path"]
)

# Domain events
DOMAIN_EVENT = Counter(
    "fitness_domain_event_total",
    "Domain analytics or business events",
    ["event"]
)

# Error counter
ERROR_COUNT = Counter(
    "fitness_error_total",
    "Count of error responses",
    ["type"]  # e.g. http_exception, validation_error, unhandled_exception
)

# Cache metrics
CACHE_OPERATIONS = Counter(
    "fitness_cache_operations_total",
    "Cache operations (hit/miss/error/invalidated)",
    ["operation"]
)

# Database metrics
DB_OPERATIONS = Counter(
    "fitness_db_operations_total",
    "Database operations",
    ["operation", "table"]
)
DB_LATENCY = Summary(
    "fitness_db_latency_seconds",
    "Database query latency in seconds",
    ["table"]
)

# Redis metrics
REDIS_OPERATIONS = Counter(
    "fitness_redis_operations_total",
    "Redis operations",
    ["operation", "success"]
)

# AI metrics
AI_PREDICTION_COUNT = Counter(
    "fitness_ai_prediction_total",
    "Count of AI model predictions",
    ["model", "status"]
)
AI_PREDICTION_LATENCY = Summary(
    "fitness_ai_prediction_latency_seconds",
    "Latency of AI model predictions in seconds",
    ["model"]
)

def start_timer() -> float:
    return time()


def observe_request(method: str, path: str, status_code: int, start_time: float) -> None:
    REQUEST_COUNT.labels(method=method, path=path, status_code=str(status_code)).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(time() - start_time)
    if status_code >= 500:
        ERROR_COUNT.labels(type="http_5xx").inc()


def record_error(error_type: str) -> None:
    ERROR_COUNT.labels(type=error_type).inc()


def record_domain_event(event: str) -> None:
    DOMAIN_EVENT.labels(event=event).inc()


def record_cache_operation(operation: str) -> None:
    CACHE_OPERATIONS.labels(operation=operation).inc()


def record_db_operation(operation: str, table: str, latency_seconds: Optional[float] = None) -> None:
    DB_OPERATIONS.labels(operation=operation, table=table).inc()
    if latency_seconds is not None:
        DB_LATENCY.labels(table=table).observe(latency_seconds)


def record_redis_operation(operation: str, success: bool) -> None:
    REDIS_OPERATIONS.labels(operation=operation, success=str(success).lower()).inc()


def record_ai_prediction(model: str, status: str, latency_seconds: float) -> None:
    AI_PREDICTION_COUNT.labels(model=model, status=status).inc()
    AI_PREDICTION_LATENCY.labels(model=model).observe(latency_seconds)


def metrics_response():
    data = generate_latest()
    return data, CONTENT_TYPE_LATEST
