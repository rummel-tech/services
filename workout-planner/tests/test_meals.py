import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Ensure path includes server root so imports resolve
    test_file = Path(__file__).resolve()
    server_root = test_file.parents[1]  # python_fastapi_server directory
    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))

    # Isolated SQLite DB for these tests
    tmp_db = os.path.join(tempfile.gettempdir(), "meals_test.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_db}"

    from database import init_sqlite  # type: ignore
    init_sqlite()
    from main import app  # type: ignore
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_data(client):
    """Get authentication token and user ID for testing"""
    response = client.post("/auth/register", json={"email": "mealsuser@example.com", "password": "TestPassword123!"})
    assert response.status_code == 201
    token = response.json()["access_token"]

    # Get user ID from /auth/me
    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    user_id = str(me_response.json()["id"])

    return {"token": token, "user_id": user_id}


@pytest.fixture(scope="module")
def auth_token(auth_data):
    """Get authentication token for testing"""
    return auth_data["token"]


@pytest.fixture(scope="module")
def user_id(auth_data):
    """Get user ID for testing"""
    return auth_data["user_id"]


def test_meals_health(client):
    """Test the meals health check endpoint"""
    r = client.get("/meals/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


def test_get_weekly_meal_plan_success(client, auth_token, user_id):
    """Test successfully getting a weekly meal plan"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    r = client.get(f"/meals/weekly-plan/{user_id}", headers=headers)
    assert r.status_code == 200

    data = r.json()
    assert data["user_id"] == user_id
    assert data["focus"] == "balanced"
    assert "days" in data
    assert len(data["days"]) == 7

    # Check structure of first day
    first_day = data["days"][0]
    assert "day" in first_day
    assert "meals" in first_day
    assert len(first_day["meals"]) > 0

    # Check structure of first meal
    first_meal = first_day["meals"][0]
    assert "name" in first_meal
    assert "calories" in first_meal


def test_get_weekly_meal_plan_with_week_start(client, auth_token, user_id):
    """Test getting weekly meal plan with week_start parameter"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    week_start = "2025-01-13"
    r = client.get(f"/meals/weekly-plan/{user_id}?week_start={week_start}", headers=headers)
    assert r.status_code == 200

    data = r.json()
    assert data["user_id"] == user_id
    assert data["week_start"] == week_start


def test_get_weekly_meal_plan_unauthorized(client):
    """Test getting meal plan without authentication"""
    r = client.get("/meals/weekly-plan/user123")
    assert r.status_code == 403


def test_get_weekly_meal_plan_wrong_user(client, auth_token):
    """Test getting meal plan for different user than authenticated"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    r = client.get("/meals/weekly-plan/different-user-id", headers=headers)
    assert r.status_code == 403


def test_get_weekly_meal_plan_all_days_present(client, auth_token, user_id):
    """Test that all 7 days of the week are returned"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    r = client.get(f"/meals/weekly-plan/{user_id}", headers=headers)
    assert r.status_code == 200

    data = r.json()
    days = [day["day"] for day in data["days"]]
    expected_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    assert days == expected_days


def test_get_weekly_meal_plan_each_day_has_meals(client, auth_token, user_id):
    """Test that each day has at least one meal"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    r = client.get(f"/meals/weekly-plan/{user_id}", headers=headers)
    assert r.status_code == 200

    data = r.json()
    for day_data in data["days"]:
        assert len(day_data["meals"]) > 0, f"Day {day_data['day']} has no meals"
        # Verify each meal has required fields
        for meal in day_data["meals"]:
            assert "name" in meal
            assert len(meal["name"]) > 0


def test_save_weekly_meal_plan_not_implemented(client, auth_token, user_id):
    """Test that saving meal plan returns 501 Not Implemented"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {
        "user_id": user_id,
        "focus": "protein",
        "days": [
            {
                "day": "Monday",
                "meals": [
                    {"name": "Protein Shake", "calories": 300, "protein_g": 50}
                ]
            }
        ]
    }
    r = client.put(f"/meals/weekly-plan/{user_id}", json=payload, headers=headers)
    assert r.status_code == 501
    assert "not implemented" in r.json()["error"]["message"].lower()


def test_save_weekly_meal_plan_unauthorized(client, user_id):
    """Test saving meal plan without authentication"""
    payload = {
        "user_id": user_id,
        "focus": "balanced",
        "days": []
    }
    r = client.put(f"/meals/weekly-plan/{user_id}", json=payload)
    assert r.status_code == 403


def test_save_weekly_meal_plan_wrong_user(client, auth_token):
    """Test saving meal plan for different user than authenticated"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {
        "user_id": "different-user",
        "focus": "balanced",
        "days": []
    }
    r = client.put("/meals/weekly-plan/different-user", json=payload, headers=headers)
    assert r.status_code == 403
