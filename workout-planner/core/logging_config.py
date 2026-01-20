"""
Logging configuration for Workout Planner.

Delegates to the common library's logging implementation.
"""

import sys
from pathlib import Path

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Re-export everything from common.logging_config
from common.logging_config import (
    init_logging,
    set_correlation_id,
    get_correlation_id,
    get_logger,
    JSONFormatter,
    correlation_id_var,
)

__all__ = [
    "init_logging",
    "set_correlation_id",
    "get_correlation_id",
    "get_logger",
    "JSONFormatter",
    "correlation_id_var",
]
