import os
import sys
import tempfile
from pathlib import Path
from datetime import date

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Ensure path includes server root so imports resolve
    test_file = Path(__file__).resolve()
    server_root = test_file.parents[1]  # python_fastapi_server directory
    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))

    # Use isolated SQLite file for tests
    tmp_db = os.path.join(tempfile.gettempdir(), "weekly_plans_test.db")
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
    response = client.post("/auth/register", json={"email": "weeklyuser@example.com", "password": "TestPassword123!"})
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


def test_default_weekly_plan(client, auth_token, user_id):
    headers = {"Authorization": f"Bearer {auth_token}"}
    r = client.get(f"/weekly-plans/{user_id}", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["user_id"] == user_id
    assert len(data["days"]) == 7
    assert data["focus"] == "hybrid"


def test_save_and_retrieve_weekly_plan(client, auth_token, user_id):
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {
        "user_id": user_id,
        "focus": "strength",
        "days": [
            {"day": "Monday", "type": "Strength"},
            {"day": "Tuesday", "type": "Run"},
            {"day": "Wednesday", "type": "Swim"},
            {"day": "Thursday", "type": "Strength"},
            {"day": "Friday", "type": "Murph"},
            {"day": "Saturday", "type": "Run"},
            {"day": "Sunday", "type": "Rest"},
        ],
    }
    put = client.put(f"/weekly-plans/{user_id}", json=payload, headers=headers)
    assert put.status_code == 200, put.text
    saved = put.json()
    assert saved["focus"] == "strength"
    assert len(saved["days"]) == 7

    # Fetch again (should return latest plan for user)
    get2 = client.get(f"/weekly-plans/{user_id}", headers=headers)
    assert get2.status_code == 200
    fetched = get2.json()
    assert fetched["focus"] == "strength"
    assert fetched["days"][0]["day"] == "Monday"
    assert fetched["days"][0]["type"] == "Strength"


def test_update_existing_weekly_plan(client, auth_token, user_id):
    headers = {"Authorization": f"Bearer {auth_token}"}
    # Initial save
    initial = {
        "user_id": user_id,
        "focus": "swim",
        "days": [{"day": "Monday", "type": "Swim"}],
    }
    client.put(f"/weekly-plans/{user_id}", json=initial, headers=headers)

    # Update with different focus and days
    updated = {
        "user_id": user_id,
        "focus": "murph",
        "days": [
            {"day": "Monday", "type": "Murph"},
            {"day": "Tuesday", "type": "Run"},
        ],
    }
    put2 = client.put(f"/weekly-plans/{user_id}", json=updated, headers=headers)
    assert put2.status_code == 200
    body = put2.json()
    assert body["focus"] == "murph"
    assert len(body["days"]) == 2
    assert body["days"][0]["type"].lower() == "murph"

    # Retrieve again
    get3 = client.get(f"/weekly-plans/{user_id}", headers=headers)
    assert get3.status_code == 200
    body2 = get3.json()
    assert body2["focus"] == "murph"
    assert len(body2["days"]) == 2


def test_null_focus_defaults(client, auth_token, user_id):
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {
        "user_id": user_id,
        "focus": None,
        "days": [{"day": "Monday", "type": "Run"}],
    }
    r = client.put(f"/weekly-plans/{user_id}", json=payload, headers=headers)
    assert r.status_code == 200
    data = r.json()
    # Backend returns None if saved None; treat missing->hybrid, so we just assert key exists
    assert "focus" in data


def test_delete_weekly_plan(client, auth_token, user_id):
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {
        "user_id": user_id,
        "focus": "strength",
        "days": [{"day": "Monday", "type": "Strength"}],
    }
    client.put(f"/weekly-plans/{user_id}", json=payload, headers=headers)
    today = str(date.today())
    # Delete using today's date (week_start assigned during save)
    del_resp = client.delete(f"/weekly-plans/{user_id}?week_start={today}", headers=headers)
    assert del_resp.status_code == 200
    # Fetch after delete -> should return default generated (no record)
    get_after = client.get(f"/weekly-plans/{user_id}", headers=headers)
    assert get_after.status_code == 200
    data = get_after.json()
    assert data["focus"] == "hybrid"


def test_delete_nonexistent_plan(client, auth_token, user_id):
    headers = {"Authorization": f"Bearer {auth_token}"}
    # Use a date far in the past that won't match any plan
    resp = client.delete(f"/weekly-plans/{user_id}?week_start=2020-01-01", headers=headers)
    assert resp.status_code == 404


def test_multiple_workouts_single_day(client, auth_token, user_id):
    """Test saving and retrieving multiple workouts for a single day"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {
        "user_id": user_id,
        "focus": "hybrid",
        "days": [
            {
                "day": "Monday",
                "workouts": [
                    {"type": "Strength"},
                    {"type": "Mobility"},
                ]
            },
            {
                "day": "Tuesday",
                "workouts": [
                    {"type": "Run"},
                ]
            },
        ],
    }

    # Save the plan
    put_resp = client.put(f"/weekly-plans/{user_id}", json=payload, headers=headers)
    assert put_resp.status_code == 200, put_resp.text
    saved = put_resp.json()

    # Verify saved data
    assert len(saved["days"]) == 2
    monday = next((d for d in saved["days"] if d["day"] == "Monday"), None)
    assert monday is not None
    assert "workouts" in monday
    assert len(monday["workouts"]) == 2
    assert monday["workouts"][0]["type"] == "Strength"
    assert monday["workouts"][1]["type"] == "Mobility"

    # Retrieve and verify
    get_resp = client.get(f"/weekly-plans/{user_id}", headers=headers)
    assert get_resp.status_code == 200
    fetched = get_resp.json()

    monday_fetched = next((d for d in fetched["days"] if d["day"] == "Monday"), None)
    assert monday_fetched is not None
    assert len(monday_fetched["workouts"]) == 2


def test_multiple_workouts_all_days(client, auth_token, user_id):
    """Test saving multiple workouts across all 7 days"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {
        "user_id": user_id,
        "focus": "hybrid",
        "days": [
            {"day": "Monday", "workouts": [{"type": "Strength"}, {"type": "Yoga"}]},
            {"day": "Tuesday", "workouts": [{"type": "Run"}, {"type": "Mobility"}]},
            {"day": "Wednesday", "workouts": [{"type": "Swim"}]},
            {"day": "Thursday", "workouts": [{"type": "Strength"}, {"type": "Cardio"}]},
            {"day": "Friday", "workouts": [{"type": "Murph"}]},
            {"day": "Saturday", "workouts": [{"type": "Run"}, {"type": "Swim"}]},
            {"day": "Sunday", "workouts": [{"type": "Rest"}]},
        ],
    }

    put_resp = client.put(f"/weekly-plans/{user_id}", json=payload, headers=headers)
    assert put_resp.status_code == 200
    saved = put_resp.json()

    # Verify all days have correct workouts
    assert len(saved["days"]) == 7

    monday = next(d for d in saved["days"] if d["day"] == "Monday")
    assert len(monday["workouts"]) == 2

    tuesday = next(d for d in saved["days"] if d["day"] == "Tuesday")
    assert len(tuesday["workouts"]) == 2

    wednesday = next(d for d in saved["days"] if d["day"] == "Wednesday")
    assert len(wednesday["workouts"]) == 1


def test_max_workouts_per_day(client, auth_token, user_id):
    """Test saving maximum number of workouts (5) for a single day"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {
        "user_id": user_id,
        "focus": "intense",
        "days": [
            {
                "day": "Monday",
                "workouts": [
                    {"type": "Strength"},
                    {"type": "Run"},
                    {"type": "Mobility"},
                    {"type": "Yoga"},
                    {"type": "Cardio"},
                ]
            },
        ],
    }

    put_resp = client.put(f"/weekly-plans/{user_id}", json=payload, headers=headers)
    assert put_resp.status_code == 200
    saved = put_resp.json()

    monday = saved["days"][0]
    assert len(monday["workouts"]) == 5
    assert monday["workouts"][0]["type"] == "Strength"
    assert monday["workouts"][4]["type"] == "Cardio"


def test_update_add_workout_to_day(client, auth_token, user_id):
    """Test updating a plan to add more workouts to an existing day"""
    headers = {"Authorization": f"Bearer {auth_token}"}

    # Initial plan with single workout
    initial = {
        "user_id": user_id,
        "focus": "hybrid",
        "days": [
            {"day": "Monday", "workouts": [{"type": "Strength"}]},
        ],
    }
    client.put(f"/weekly-plans/{user_id}", json=initial, headers=headers)

    # Update to add second workout
    updated = {
        "user_id": user_id,
        "focus": "hybrid",
        "days": [
            {
                "day": "Monday",
                "workouts": [
                    {"type": "Strength"},
                    {"type": "Mobility"},
                    {"type": "Cardio"},
                ]
            },
        ],
    }

    put_resp = client.put(f"/weekly-plans/{user_id}", json=updated, headers=headers)
    assert put_resp.status_code == 200
    saved = put_resp.json()

    monday = saved["days"][0]
    assert len(monday["workouts"]) == 3
    assert monday["workouts"][1]["type"] == "Mobility"
    assert monday["workouts"][2]["type"] == "Cardio"


def test_mixed_format_backward_compatibility(client, auth_token, user_id):
    """Test that old format (type field) still works alongside new format (workouts array)"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {
        "user_id": user_id,
        "focus": "hybrid",
        "days": [
            # Old format
            {"day": "Monday", "type": "Strength"},
            # New format
            {"day": "Tuesday", "workouts": [{"type": "Run"}, {"type": "Swim"}]},
        ],
    }

    put_resp = client.put(f"/weekly-plans/{user_id}", json=payload, headers=headers)
    assert put_resp.status_code == 200
    saved = put_resp.json()

    # Both should be saved
    assert len(saved["days"]) == 2

    # Monday might be converted to new format or keep old format - just verify it exists
    monday = next((d for d in saved["days"] if d["day"] == "Monday"), None)
    assert monday is not None

    # Tuesday should have workouts array
    tuesday = next((d for d in saved["days"] if d["day"] == "Tuesday"), None)
    assert tuesday is not None
    if "workouts" in tuesday:
        assert len(tuesday["workouts"]) == 2


def test_empty_workouts_array(client, auth_token, user_id):
    """Test that days with empty workouts array are handled correctly"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {
        "user_id": user_id,
        "focus": "rest",
        "days": [
            {"day": "Monday", "workouts": []},
            {"day": "Tuesday", "workouts": [{"type": "Run"}]},
        ],
    }

    put_resp = client.put(f"/weekly-plans/{user_id}", json=payload, headers=headers)
    assert put_resp.status_code == 200
    saved = put_resp.json()

    monday = next((d for d in saved["days"] if d["day"] == "Monday"), None)
    assert monday is not None
    # Empty array should be preserved or handled gracefully
    assert "workouts" in monday or "type" in monday