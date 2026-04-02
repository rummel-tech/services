"""Tests for education-planner goals endpoints."""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DB = os.path.join(tempfile.gettempdir(), "edu_goals_test.db")

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
    r = client.get("/education/api/v1/goals")
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert "meta" in data
    assert isinstance(data["data"], list)


def test_create_goal(client):
    payload = {
        "title": "Learn Python",
        "description": "Master Python programming",
        "category": "professional",
        "target_date": "2025-12-31",
    }
    r = client.post("/education/api/v1/goals", json=payload)
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["title"] == "Learn Python"
    assert data["category"] == "professional"
    assert "id" in data
    assert data["is_completed"] is False


def test_create_goal_missing_title(client):
    r = client.post("/education/api/v1/goals", json={"category": "personal"})
    assert r.status_code == 422


def test_create_goal_invalid_category(client):
    r = client.post("/education/api/v1/goals", json={"title": "Test", "category": "invalid_cat"})
    assert r.status_code == 400


def test_get_goal(client):
    r = client.post("/education/api/v1/goals", json={"title": "Read books", "category": "personal"})
    assert r.status_code == 201
    goal_id = r.json()["data"]["id"]

    r = client.get(f"/education/api/v1/goals/{goal_id}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["id"] == goal_id
    assert data["title"] == "Read books"
    assert "activities_count" in data


def test_get_goal_not_found(client):
    r = client.get("/education/api/v1/goals/nonexistent-id")
    assert r.status_code == 404


def test_update_goal(client):
    r = client.post("/education/api/v1/goals", json={"title": "Goal to update", "category": "academic"})
    assert r.status_code == 201
    goal_id = r.json()["data"]["id"]

    r = client.put(f"/education/api/v1/goals/{goal_id}", json={
        "title": "Updated Goal",
        "is_completed": True,
    })
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["title"] == "Updated Goal"
    assert data["is_completed"] is True
    assert data["completed_at"] is not None


def test_update_goal_not_found(client):
    r = client.put("/education/api/v1/goals/nonexistent-id", json={"title": "Ghost"})
    assert r.status_code == 404


def test_update_goal_invalid_category(client):
    r = client.post("/education/api/v1/goals", json={"title": "Cat test", "category": "personal"})
    goal_id = r.json()["data"]["id"]
    r = client.put(f"/education/api/v1/goals/{goal_id}", json={"category": "invalid"})
    assert r.status_code == 400


def test_delete_goal(client):
    r = client.post("/education/api/v1/goals", json={"title": "To delete", "category": "personal"})
    assert r.status_code == 201
    goal_id = r.json()["data"]["id"]

    r = client.delete(f"/education/api/v1/goals/{goal_id}")
    assert r.status_code == 204

    r = client.get(f"/education/api/v1/goals/{goal_id}")
    assert r.status_code == 404


def test_delete_goal_not_found(client):
    r = client.delete("/education/api/v1/goals/nonexistent-id")
    assert r.status_code == 404


def test_list_goals_filter_active(client):
    r = client.get("/education/api/v1/goals?status=active")
    assert r.status_code == 200
    data = r.json()
    assert all(not g["is_completed"] for g in data["data"])


def test_list_goals_filter_completed(client):
    r = client.post("/education/api/v1/goals", json={"title": "Completed goal", "category": "personal"})
    goal_id = r.json()["data"]["id"]
    client.put(f"/education/api/v1/goals/{goal_id}", json={"is_completed": True})

    r = client.get("/education/api/v1/goals?status=completed")
    assert r.status_code == 200
    data = r.json()
    assert all(g["is_completed"] for g in data["data"])


def test_list_goals_pagination(client):
    r = client.get("/education/api/v1/goals?limit=2&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert "meta" in data
    assert data["meta"]["limit"] == 2
