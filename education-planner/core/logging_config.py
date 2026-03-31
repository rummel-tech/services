"""Logging configuration — delegates to common library."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.logging_config import (
    init_logging,
    set_correlation_id,
    get_correlation_id,
    get_logger,
    JSONFormatter,
    correlation_id_var,
)

__all__ = [
    'init_logging',
    'set_correlation_id',
    'get_correlation_id',
    'get_logger',
    'JSONFormatter',
    'correlation_id_var',
]
