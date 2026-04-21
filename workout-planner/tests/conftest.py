"""
Pytest configuration for workout-planner tests.

Note: Each test file defines its own fixtures with isolated databases.
This conftest only provides shared utilities.
"""
import os
import sys

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Disable Prometheus metrics in tests to avoid "Duplicated timeseries" errors
# when multiple test modules each instantiate the app
os.environ.setdefault("ENABLE_METRICS", "false")

import pytest
from unittest.mock import MagicMock


# Note: Don't import main or app here - each test file creates its own
# app instance with an isolated database to prevent cross-test contamination


@pytest.fixture
def mock_ai_engine():
    """Create a mocked AI engine for tests that need it."""
    from ai_engine import AIFitnessEngine
    mock_engine = MagicMock(spec=AIFitnessEngine)
    mock_engine.generate_daily_plan.return_value = {"daily_plan": "mock"}
    mock_engine.generate_weekly_plan.return_value = {"weekly_plan": "mock"}
    return mock_engine
