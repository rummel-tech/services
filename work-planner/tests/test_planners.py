"""Tests for work-planner planners (day planners, tasks, week planners) endpoints."""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DB = os.path.join(tempfile.gettempdir(), "work_planners_test.db")

os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["REDIS_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "development"
os.environ["DISABLE_AUTH"] = "true"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def client():
    from main import app  # noqa: PLC0415
    return TestClient(app)


# ---------------------------------------------------------------------------
# Day Planner tests
# ---------------------------------------------------------------------------

def test_list_day_planners_empty(client):
    r = client.get("/day-planners")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_day_planner(client):
    r = client.post("/day-planners", json={"date": "2025-06-02", "notes": "Busy day"})
    assert r.status_code == 201
    data = r.json()
    assert data["date"] == "2025-06-02"
    assert data["notes"] == "Busy day"
    assert "id" in data
    assert isinstance(data["tasks"], list)


def test_create_day_planner_idempotent(client):
    r1 = client.post("/day-planners", json={"date": "2025-06-10"})
    assert r1.status_code == 201
    r2 = client.post("/day-planners", json={"date": "2025-06-10"})
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


def test_get_day_planner(client):
    client.post("/day-planners", json={"date": "2025-06-03"})
    r = client.get("/day-planners/2025-06-03")
    assert r.status_code == 200
    assert r.json()["date"] == "2025-06-03"


def test_get_day_planner_not_found(client):
    r = client.get("/day-planners/2099-01-01")
    assert r.status_code == 404


def test_update_day_planner_notes(client):
    client.post("/day-planners", json={"date": "2025-06-04"})
    r = client.patch("/day-planners/2025-06-04", json={"notes": "Updated notes"})
    assert r.status_code == 200
    assert r.json()["notes"] == "Updated notes"


def test_update_day_planner_not_found(client):
    r = client.patch("/day-planners/2099-12-31", json={"notes": "Ghost"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Task tests
# ---------------------------------------------------------------------------

def test_create_task(client):
    client.post("/day-planners", json={"date": "2025-06-05"})
    r = client.post("/day-planners/2025-06-05/tasks", json={
        "title": "Write report",
        "priority": "high",
        "duration_minutes": 60,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Write report"
    assert data["priority"] == "high"
    assert data["completed"] is False


def test_create_task_creates_day_planner_if_missing(client):
    r = client.post("/day-planners/2025-07-15/tasks", json={
        "title": "Auto-created planner task",
        "priority": "medium",
    })
    assert r.status_code == 201
    assert r.json()["title"] == "Auto-created planner task"


def test_create_task_missing_title(client):
    client.post("/day-planners", json={"date": "2025-06-06"})
    r = client.post("/day-planners/2025-06-06/tasks", json={"priority": "low"})
    assert r.status_code == 422


def test_list_tasks(client):
    r = client.get("/tasks")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_update_task(client):
    client.post("/day-planners", json={"date": "2025-06-07"})
    r = client.post("/day-planners/2025-06-07/tasks", json={
        "title": "Task to update",
        "priority": "medium",
    })
    task_id = r.json()["id"]

    r = client.patch(f"/tasks/{task_id}", json={"completed": True, "title": "Updated task"})
    assert r.status_code == 200
    assert r.json()["completed"] is True
    assert r.json()["title"] == "Updated task"


def test_update_task_not_found(client):
    r = client.patch("/tasks/nonexistent-task", json={"completed": True})
    assert r.status_code == 404


def test_delete_task(client):
    client.post("/day-planners", json={"date": "2025-06-08"})
    r = client.post("/day-planners/2025-06-08/tasks", json={
        "title": "Task to delete",
        "priority": "low",
    })
    task_id = r.json()["id"]

    r = client.delete(f"/tasks/{task_id}")
    assert r.status_code == 204

    r = client.patch(f"/tasks/{task_id}", json={"completed": True})
    assert r.status_code == 404


def test_delete_task_not_found(client):
    r = client.delete("/tasks/nonexistent-task")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Week Planner tests
# ---------------------------------------------------------------------------

def test_create_week_planner(client):
    r = client.post("/week-planners", json={
        "week_start_date": "2025-06-02",
        "weekly_goals": ["Ship feature X", "Code review Y"],
        "notes": "Important week",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["week_start_date"] == "2025-06-02"
    assert "id" in data
    assert isinstance(data["day_planners"], list)


def test_create_week_planner_idempotent(client):
    r1 = client.post("/week-planners", json={"week_start_date": "2025-06-16"})
    assert r1.status_code == 201
    r2 = client.post("/week-planners", json={"week_start_date": "2025-06-16"})
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


def test_get_week_planner(client):
    client.post("/week-planners", json={"week_start_date": "2025-06-09"})
    r = client.get("/week-planners/2025-06-09")
    assert r.status_code == 200
    assert r.json()["week_start_date"] == "2025-06-09"


def test_get_week_planner_not_found(client):
    r = client.get("/week-planners/2099-01-06")
    assert r.status_code == 404


def test_update_week_planner(client):
    client.post("/week-planners", json={"week_start_date": "2025-06-23"})
    r = client.patch("/week-planners/2025-06-23", json={
        "weekly_goals": ["Updated goal"],
        "notes": "New notes",
    })
    assert r.status_code == 200
    assert r.json()["notes"] == "New notes"


def test_update_week_planner_not_found(client):
    r = client.patch("/week-planners/2099-06-23", json={"notes": "Ghost"})
    assert r.status_code == 404


def test_week_stats_no_tasks(client):
    client.post("/week-planners", json={"week_start_date": "2025-07-07"})
    r = client.get("/week-planners/2025-07-07/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_tasks"] == 0
    assert data["completed_tasks"] == 0
    assert data["completion_rate"] == 0.0


def test_week_stats_with_tasks(client):
    client.post("/week-planners", json={"week_start_date": "2025-07-14"})
    client.post("/day-planners/2025-07-14/tasks", json={"title": "Task A", "priority": "high"})
    client.post("/day-planners/2025-07-15/tasks", json={"title": "Task B", "priority": "medium"})

    r = client.get("/week-planners/2025-07-14/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_tasks"] >= 2
    assert "completion_rate" in data
