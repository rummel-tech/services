"""Tests for work-planner plans endpoints."""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DB = os.path.join(tempfile.gettempdir(), "work_plans_test.db")

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
def goal_id(client):
    r = client.post("/goals", json={"title": "Career Growth", "goal_type": "corporate"})
    assert r.status_code == 201
    return r.json()["id"]


def test_list_plans_empty(client):
    r = client.get("/plans")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_plan(client, goal_id):
    payload = {
        "goal_id": goal_id,
        "title": "Q1 Execution Plan",
        "description": "First quarter action items",
        "status": "active",
        "steps": ["Step 1", "Step 2"],
    }
    r = client.post("/plans", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Q1 Execution Plan"
    assert data["goal_id"] == goal_id
    assert "id" in data
    assert data["steps"] == ["Step 1", "Step 2"]


def test_create_plan_invalid_goal(client):
    r = client.post("/plans", json={"goal_id": "nonexistent-goal", "title": "Orphan Plan"})
    assert r.status_code == 404


def test_create_plan_missing_title(client, goal_id):
    r = client.post("/plans", json={"goal_id": goal_id})
    assert r.status_code == 422


def test_get_plan(client, goal_id):
    r = client.post("/plans", json={"goal_id": goal_id, "title": "Fetched Plan"})
    assert r.status_code == 201
    plan_id = r.json()["id"]

    r = client.get(f"/plans/{plan_id}")
    assert r.status_code == 200
    assert r.json()["id"] == plan_id
    assert r.json()["title"] == "Fetched Plan"


def test_get_plan_not_found(client):
    r = client.get("/plans/nonexistent-id")
    assert r.status_code == 404


def test_update_plan(client, goal_id):
    r = client.post("/plans", json={"goal_id": goal_id, "title": "Plan to Update"})
    assert r.status_code == 201
    plan_id = r.json()["id"]

    r = client.patch(f"/plans/{plan_id}", json={"status": "completed", "title": "Updated Plan"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert data["title"] == "Updated Plan"


def test_update_plan_not_found(client):
    r = client.patch("/plans/nonexistent-id", json={"status": "completed"})
    assert r.status_code == 404


def test_delete_plan(client, goal_id):
    r = client.post("/plans", json={"goal_id": goal_id, "title": "Plan to Delete"})
    assert r.status_code == 201
    plan_id = r.json()["id"]

    r = client.delete(f"/plans/{plan_id}")
    assert r.status_code == 204

    r = client.get(f"/plans/{plan_id}")
    assert r.status_code == 404


def test_delete_plan_not_found(client):
    r = client.delete("/plans/nonexistent-id")
    assert r.status_code == 404


def test_list_plans_filtered_by_goal(client, goal_id):
    r = client.post("/plans", json={"goal_id": goal_id, "title": "Filtered Plan"})
    assert r.status_code == 201

    r = client.get(f"/plans?goal_id={goal_id}")
    assert r.status_code == 200
    plans = r.json()
    assert all(p["goal_id"] == goal_id for p in plans)


def test_list_plans_filtered_by_status(client, goal_id):
    r = client.post("/plans", json={"goal_id": goal_id, "title": "Active Plan", "status": "active"})
    assert r.status_code == 201

    r = client.get("/plans?plan_status=active")
    assert r.status_code == 200
    plans = r.json()
    assert all(p["status"] == "active" for p in plans)
