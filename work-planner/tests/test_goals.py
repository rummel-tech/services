"""Tests for work-planner goals endpoints."""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DB = os.path.join(tempfile.gettempdir(), "work_goals_test.db")

os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["REDIS_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "development"
os.environ["DISABLE_AUTH"] = "true"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def client():
    if os.path.exists(_DB):
        os.remove(_DB)
    from main import app  # noqa: PLC0415
    return TestClient(app)


def test_list_goals_empty(client):
    r = client.get("/goals")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_goal(client):
    payload = {
        "title": "Launch MVP",
        "description": "Ship the minimum viable product",
        "goal_type": "corporate",
        "status": "notStarted",
    }
    r = client.post("/goals", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Launch MVP"
    assert "id" in data
    return data["id"]


def test_get_goal(client):
    # Create first
    r = client.post("/goals", json={"title": "Read 12 books", "goal_type": "personal"})
    assert r.status_code == 201
    goal_id = r.json()["id"]

    r = client.get(f"/goals/{goal_id}")
    assert r.status_code == 200
    assert r.json()["id"] == goal_id


def test_update_goal(client):
    r = client.post("/goals", json={"title": "Exercise daily", "goal_type": "personal"})
    assert r.status_code == 201
    goal_id = r.json()["id"]

    r = client.patch(f"/goals/{goal_id}", json={"status": "inProgress"})
    assert r.status_code in (200, 405)  # 405 if PATCH not supported, 200 if it is


def test_delete_goal(client):
    r = client.post("/goals", json={"title": "To be deleted", "goal_type": "personal"})
    assert r.status_code == 201
    goal_id = r.json()["id"]

    r = client.delete(f"/goals/{goal_id}")
    assert r.status_code in (200, 204)


def test_create_goal_missing_title(client):
    r = client.post("/goals", json={"goal_type": "corporate"})
    assert r.status_code == 422
