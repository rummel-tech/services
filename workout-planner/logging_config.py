import json
import logging
import time
import uuid
import traceback
import contextvars
from typing import Any, Dict, Set
from settings import get_settings

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)

# Whitelist of standard LogRecord attributes to include in the JSON output.
# This is a safer approach than a blacklist, as it prevents accidental logging of sensitive info.
# See: https://docs.python.org/3/library/logging.html#logrecord-attributes
LOG_RECORD_WHITELIST: Set[str] = {
    "name", "levelname", "pathname", "lineno", "funcName", "exc_info", "exc_text", "stack_info"
}

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        settings = get_settings()
        log_record: Dict[str, Any] = {
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "app_name": settings.app_name,
            "environment": settings.environment,
        }

        corr_id = correlation_id_var.get()
        if corr_id:
            log_record["correlation_id"] = corr_id

        # Add whitelisted LogRecord attributes
        for key, value in record.__dict__.items():
            if key in LOG_RECORD_WHITELIST and value is not None:
                log_record[key] = value

        # Add any extra attributes passed to the logger.
        # This allows for logging of custom context.
        extra_attrs = {k: v for k, v in record.__dict__.items() if k not in log_record and not k.startswith("_")}
        if extra_attrs:
            log_record.update(extra_attrs)

        if record.exc_info:
            log_record["traceback"] = traceback.format_exception(*record.exc_info)
        elif record.exc_text:
            log_record["traceback"] = record.exc_text

        return json.dumps(log_record, ensure_ascii=False, default=str)


def init_logging():
    settings = get_settings()
    root = logging.getLogger()
    # Clear existing handlers
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)


def set_correlation_id(value: str | None = None) -> str:
    cid = value or str(uuid.uuid4())
    correlation_id_var.set(cid)
    return cid


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
