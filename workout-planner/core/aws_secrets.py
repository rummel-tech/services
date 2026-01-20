"""
AWS Secrets Manager integration for Workout Planner.

Delegates to the common library's implementation.
"""

import sys
from pathlib import Path

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.aws_secrets import (
    load_secret_from_aws,
    inject_secrets_from_aws,
)

__all__ = [
    "load_secret_from_aws",
    "inject_secrets_from_aws",
]
