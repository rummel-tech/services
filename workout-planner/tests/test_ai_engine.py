import pytest
from ai_engine import AIFitnessEngine


@pytest.fixture
def engine():
    return AIFitnessEngine()


def test_generate_daily_plan(engine):
    user_data = {"hrv": 60, "sleep_hours": 8, "resting_hr": 55}
    result = engine.generate_daily_plan(user_data)

    # The actual implementation returns "readiness" and "plan"
    assert "readiness" in result
    assert "plan" in result


def test_generate_weekly_plan(engine):
    user_data = {"goal": "strength"}
    result = engine.generate_weekly_plan(user_data)

    # The actual implementation returns the weekly plan structure
    assert result is not None
