"""
Common utilities and base classes for all services.

This package provides production-ready features:
- FastAPI app factory with standard configuration
- Structured JSON logging with correlation IDs
- Security headers middleware
- Prometheus metrics
- Redis caching with graceful fallback
- AWS Secrets Manager integration
- Pydantic settings management
"""

from .app_factory import create_app, ServiceConfig
from .utils import day_name_from_date, parse_date
from .middleware import add_standard_middleware, get_correlation_id
from .error_handlers import install_error_handlers
from .settings import BaseServiceSettings, get_settings, clear_settings_cache
from .logging_config import (
    init_logging,
    set_correlation_id,
    get_logger,
    JSONFormatter,
    correlation_id_var,
)
from .aws_secrets import inject_secrets_from_aws, load_secret_from_aws
from . import metrics
from . import redis_client
from . import cache

__all__ = [
    # App factory
    "create_app",
    "ServiceConfig",
    # Utils
    "day_name_from_date",
    "parse_date",
    # Middleware
    "add_standard_middleware",
    "get_correlation_id",
    # Error handlers
    "install_error_handlers",
    # Settings
    "BaseServiceSettings",
    "get_settings",
    "clear_settings_cache",
    # Logging
    "init_logging",
    "set_correlation_id",
    "get_logger",
    "JSONFormatter",
    "correlation_id_var",
    # AWS
    "inject_secrets_from_aws",
    "load_secret_from_aws",
    # Modules
    "metrics",
    "redis_client",
    "cache",
]
