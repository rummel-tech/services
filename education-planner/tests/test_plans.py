"""Tests for education-planner plans (weekly plans + activities) endpoints."""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DB = os.path.join(tempfile.gettempdir(), "edu_plans_test.db")

os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["REDIS_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "development"
os.environ["DISABLE_AUTH"] = "true"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def client():
    from main import app  # noqa: PLC0415
    return TestClient(app)


@pytest.fixture(scope="module")
def plan_id(client):
    r = client.post("/education/api/v1/plans", json={
        "title": "Week 1 Learning",
        "week_start_date": "2025-06-02",
    })
    assert r.status_code == 201
    return r.json()["data"]["id"]


def test_list_plans_empty(client):
    r = client.get("/education/api/v1/plans")
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert "meta" in data


def test_create_plan(client):
    r = client.post("/education/api/v1/plans", json={
        "title": "Week 2 Learning",
        "week_start_date": "2025-06-09",
    })
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["title"] == "Week 2 Learning"
    assert "id" in data
    assert isinstance(data["activities"], list)


def test_create_plan_normalizes_to_monday(client):
    r = client.post("/education/api/v1/plans", json={
        "title": "Wednesday Week",
        "week_start_date": "2025-06-18",
    })
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["week_start_date"] == "2025-06-16"


def test_create_plan_duplicate_week(client):
    client.post("/education/api/v1/plans", json={
        "title": "Dup Week",
        "week_start_date": "2025-07-07",
    })
    r = client.post("/education/api/v1/plans", json={
        "title": "Dup Week 2",
        "week_start_date": "2025-07-07",
    })
    assert r.status_code == 409


def test_create_plan_missing_title(client):
    r = client.post("/education/api/v1/plans", json={"week_start_date": "2025-08-04"})
    assert r.status_code == 422


def test_get_plan(client, plan_id):
    r = client.get(f"/education/api/v1/plans/{plan_id}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["id"] == plan_id
    assert "activities" in data


def test_get_plan_not_found(client):
    r = client.get("/education/api/v1/plans/nonexistent-id")
    assert r.status_code == 404


def test_add_activity(client, plan_id):
    r = client.post(f"/education/api/v1/plans/{plan_id}/activities", json={
        "title": "Read chapter 5",
        "duration_minutes": 45,
        "scheduled_time": "2025-06-02T09:00:00",
    })
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["title"] == "Read chapter 5"
    assert data["duration_minutes"] == 45
    assert data["is_completed"] is False


def test_add_activity_invalid_plan(client):
    r = client.post("/education/api/v1/plans/nonexistent-id/activities", json={
        "title": "Orphan activity",
        "duration_minutes": 30,
        "scheduled_time": "2025-06-02T10:00:00",
    })
    assert r.status_code == 404


def test_update_activity(client, plan_id):
    r = client.post(f"/education/api/v1/plans/{plan_id}/activities", json={
        "title": "Study session",
        "duration_minutes": 60,
        "scheduled_time": "2025-06-03T14:00:00",
    })
    activity_id = r.json()["data"]["id"]

    r = client.patch(
        f"/education/api/v1/plans/{plan_id}/activities/{activity_id}",
        json={"is_completed": True, "actual_minutes": 55},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["is_completed"] is True
    assert data["completed_at"] is not None


def test_delete_activity(client, plan_id):
    r = client.post(f"/education/api/v1/plans/{plan_id}/activities", json={
        "title": "Activity to delete",
        "duration_minutes": 20,
        "scheduled_time": "2025-06-04T08:00:00",
    })
    activity_id = r.json()["data"]["id"]

    r = client.delete(f"/education/api/v1/plans/{plan_id}/activities/{activity_id}")
    assert r.status_code == 204


def test_list_plans_filter_by_week(client):
    r = client.get("/education/api/v1/plans?week_start=2025-06-02")
    assert r.status_code == 200
    data = r.json()
    assert all(p["week_start_date"] == "2025-06-02" for p in data["data"])


def test_plan_completion_percentage(client, plan_id):
    r = client.get(f"/education/api/v1/plans/{plan_id}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert "completion_percentage" in data
    assert "total_planned_minutes" in data
