import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import sys
import os

# Add the project root to the path so that we can import the app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app
from ai_engine import AIFitnessEngine

@pytest.fixture(scope="module")
def test_client():
    # Mock the AIFitnessEngine to avoid external API calls during tests
    mock_engine = MagicMock(spec=AIFitnessEngine)
    mock_engine.generate_daily_plan.return_value = {"daily_plan": "mock"}
    mock_engine.generate_weekly_plan.return_value = {"weekly_plan": "mock"}
    app.dependency_overrides[AIFitnessEngine] = lambda: mock_engine

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()
