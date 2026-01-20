"""
Structured JSON logging configuration for all services.

Provides consistent log formatting with correlation IDs,
timestamps, and structured metadata.
"""

import json
import logging
import time
import uuid
import traceback
import contextvars
from typing import Any, Dict, Set, Optional

# Context variable for request correlation ID
correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)

# Whitelist of standard LogRecord attributes to include in JSON output
LOG_RECORD_WHITELIST: Set[str] = {
    "name", "levelname", "pathname", "lineno", "funcName",
    "exc_info", "exc_text", "stack_info"
}


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Output format:
    {
        "timestamp": "2025-01-16T12:00:00",
        "level": "info",
        "logger": "app.request",
        "message": "request_start",
        "app_name": "my-service",
        "environment": "development",
        "correlation_id": "uuid-here",
        ...extra fields
    }
    """

    def __init__(self, app_name: str = "service", environment: str = "development"):
        super().__init__()
        self.app_name = app_name
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "app_name": self.app_name,
            "environment": self.environment,
        }

        # Add correlation ID if set
        corr_id = correlation_id_var.get()
        if corr_id:
            log_record["correlation_id"] = corr_id

        # Add whitelisted LogRecord attributes
        for key, value in record.__dict__.items():
            if key in LOG_RECORD_WHITELIST and value is not None:
                log_record[key] = value

        # Add any extra attributes passed to the logger
        extra_attrs = {
            k: v for k, v in record.__dict__.items()
            if k not in log_record
            and not k.startswith("_")
            and k not in {"args", "msg", "created", "msecs", "relativeCreated",
                         "levelno", "process", "processName", "thread", "threadName",
                         "taskName", "filename", "module"}
        }
        if extra_attrs:
            log_record.update(extra_attrs)

        # Add traceback if present
        if record.exc_info:
            log_record["traceback"] = traceback.format_exception(*record.exc_info)
        elif record.exc_text:
            log_record["traceback"] = record.exc_text

        return json.dumps(log_record, ensure_ascii=False, default=str)


def init_logging(
    app_name: str = "service",
    environment: str = "development",
    log_level: str = "info"
) -> None:
    """
    Initialize structured JSON logging.

    Args:
        app_name: Application name for log records
        environment: Environment name (development/staging/production)
        log_level: Log level (debug/info/warning/error/critical)
    """
    root = logging.getLogger()

    # Clear existing handlers
    for handler in list(root.handlers):
        root.removeHandler(handler)

    # Set level
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Add JSON handler
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter(app_name=app_name, environment=environment))
    root.addHandler(handler)


def set_correlation_id(value: Optional[str] = None) -> str:
    """
    Set the correlation ID for the current request context.

    Args:
        value: Correlation ID to set, or None to generate a new one

    Returns:
        The correlation ID that was set
    """
    cid = value or str(uuid.uuid4())
    correlation_id_var.set(cid)
    return cid


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID."""
    return correlation_id_var.get()


def get_logger(name: str) -> logging.Logger:
    """Get a logger by name."""
    return logging.getLogger(name)
