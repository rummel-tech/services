import pytest
from unittest.mock import MagicMock
from ai_engine import AIFitnessEngine

@pytest.fixture
def mock_model():
    return MagicMock()

@pytest.fixture
def engine(mock_model):
    return AIFitnessEngine(model=mock_model)

def test_generate_daily_plan(engine, mock_model):
    user_data = {"hrv": 60, "sleep_hours": 8, "resting_hr": 55}
    mock_model.predict.return_value = [0.8]  # Mock the model's prediction
    result = engine.generate_daily_plan(user_data)

    assert "readiness_score" in result
    assert result["readiness_score"] == 0.8
    assert "daily_plan" in result

def test_generate_weekly_plan(engine, mock_model):
    user_data = {"goal": "strength"}
    mock_model.predict.return_value = [0.7]  # Mock the model's prediction
    result = engine.generate_weekly_plan(user_data)

    assert "weekly_plan" in result
    assert "focus" in result["weekly_plan"]
    assert result["weekly_plan"]["focus"] == "strength"
