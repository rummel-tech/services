"""Tests for Artemis contract endpoints in the workout-planner service."""
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from test_helpers import get_next_registration_code, setup_test_database


@pytest.fixture(scope="module")
def client():
    test_file = Path(__file__).resolve()
    server_root = test_file.parents[1]
    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))

    tmp_db = os.path.join(tempfile.gettempdir(), "artemis_test.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)

    setup_test_database(tmp_db)

    from main import app  # type: ignore
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_data(client):
    code = get_next_registration_code()
    r = client.post("/auth/register", json={
        "email": "artemis_test@example.com",
        "password": "TestPassword123!",
        "registration_code": code,
    })
    assert r.status_code == 201
    token = r.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    return {"token": token, "user_id": me.json()["id"]}


@pytest.fixture(scope="module")
def token(auth_data):
    return auth_data["token"]


@pytest.fixture(scope="module")
def user_id(auth_data):
    return auth_data["user_id"]


def headers(token):
    return {"Authorization": f"Bearer {token}"}


# --- Manifest ---

def test_manifest_no_auth(client):
    r = client.get("/artemis/manifest")
    assert r.status_code == 200
    data = r.json()
    assert data["module"]["id"] == "workout-planner"
    assert data["module"]["contract_version"] == "1.0"
    assert len(data["capabilities"]["dashboard_widgets"]) == 3
    assert len(data["capabilities"]["agent_tools"]) == 4


# --- Widgets ---

def test_widget_todays_workout_no_plan(client, token):
    r = client.get("/artemis/widgets/todays_workout", headers=headers(token))
    assert r.status_code == 200
    data = r.json()
    assert data["widget_id"] == "todays_workout"
    assert data["data"]["has_workout"] is False


def test_widget_weekly_progress(client, token):
    r = client.get("/artemis/widgets/weekly_progress", headers=headers(token))
    assert r.status_code == 200
    data = r.json()
    assert data["widget_id"] == "weekly_progress"
    assert "planned" in data["data"]
    assert "completed" in data["data"]


def test_widget_readiness_score(client, token):
    r = client.get("/artemis/widgets/readiness_score", headers=headers(token))
    assert r.status_code == 200
    data = r.json()
    assert data["widget_id"] == "readiness_score"
    assert "score" in data["data"]


def test_widget_unknown_404(client, token):
    r = client.get("/artemis/widgets/nonexistent", headers=headers(token))
    assert r.status_code == 404


def test_widget_requires_auth(client):
    r = client.get("/artemis/widgets/todays_workout")
    assert r.status_code == 401


# --- Agent tools ---

def test_agent_schedule_workout(client, token, user_id):
    target_date = str(date.today())
    r = client.post("/artemis/agent/schedule_workout", json={
        "type": "strength",
        "date": target_date,
        "duration_minutes": 60,
        "notes": "Artemis scheduled",
    }, headers=headers(token))
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["result"]["date"] == target_date
    assert data["result"]["type"] == "strength"


def test_agent_get_todays_workout_after_schedule(client, token):
    r = client.get("/artemis/agent/get_todays_workout", headers=headers(token))
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    # Plan was just scheduled
    assert data["result"]["has_workout"] is True
    assert len(data["result"]["workouts"]) == 1


def test_widget_todays_workout_after_schedule(client, token):
    r = client.get("/artemis/widgets/todays_workout", headers=headers(token))
    assert r.status_code == 200
    assert r.json()["data"]["has_workout"] is True


def test_agent_log_workout(client, token):
    r = client.post("/artemis/agent/log_workout", json={
        "type": "run",
        "duration_minutes": 30,
        "notes": "5k easy",
    }, headers=headers(token))
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["result"]["type"] == "run"


def test_agent_log_workout_missing_type(client, token):
    r = client.post("/artemis/agent/log_workout", json={"duration_minutes": 30}, headers=headers(token))
    assert r.status_code == 400


def test_agent_get_weekly_summary(client, token):
    r = client.get("/artemis/agent/get_weekly_summary", headers=headers(token))
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert "week_start" in data["result"]
    assert "planned" in data["result"]


# --- Data endpoints ---

def test_data_calories_burned(client, token):
    r = client.get(f"/artemis/data/calories_burned?date={date.today()}", headers=headers(token))
    assert r.status_code == 200
    data = r.json()
    assert data["data_id"] == "calories_burned"
    assert "calories" in data["data"]


def test_data_readiness_score(client, token):
    r = client.get("/artemis/data/readiness_score", headers=headers(token))
    assert r.status_code == 200
    assert r.json()["data_id"] == "readiness_score"


def test_data_workout_schedule(client, token):
    r = client.get("/artemis/data/workout_schedule", headers=headers(token))
    assert r.status_code == 200
    data = r.json()
    assert data["data_id"] == "workout_schedule"
    assert "workouts" in data["data"]
    assert "date_range" in data["data"]


def test_data_unknown_404(client, token):
    r = client.get("/artemis/data/unknown_id", headers=headers(token))
    assert r.status_code == 404
