"""Tests for home-manager CRUD API: tasks, goals, assets."""
import pytest


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_ready(self, client):
        r = client.get("/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    def test_security_headers(self, client):
        r = client.get("/health")
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"

    def test_correlation_id_header(self, client):
        r = client.get("/health")
        assert "x-request-id" in r.headers


# ---------------------------------------------------------------------------
# Tasks CRUD
# ---------------------------------------------------------------------------

class TestTasks:
    def test_list_tasks_empty(self, client):
        r = client.get("/tasks/no-such-user")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_task(self, client):
        payload = {
            "user_id": "user-123",
            "title": "Fix leaky faucet",
            "category": "plumbing",
            "priority": "high",
        }
        r = client.post("/tasks", json=payload)
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == "Fix leaky faucet"
        assert data["user_id"] == "user-123"
        assert data["category"] == "plumbing"
        assert "id" in data
        return data["id"]

    def test_create_task_missing_required(self, client):
        r = client.post("/tasks", json={"user_id": "user-123"})
        assert r.status_code == 422

    def test_list_tasks_after_create(self, client):
        client.post("/tasks", json={
            "user_id": "list-test-user",
            "title": "Mow lawn",
            "category": "yard",
        })
        r = client.get("/tasks/list-test-user")
        assert r.status_code == 200
        tasks = r.json()
        assert isinstance(tasks, list)
        assert len(tasks) >= 1
        assert tasks[0]["title"] == "Mow lawn"

    def test_get_task_by_id(self, client):
        created = client.post("/tasks", json={
            "user_id": "get-test-user",
            "title": "Replace filter",
            "category": "maintenance",
        }).json()
        task_id = created["id"]

        r = client.get(f"/tasks/get-test-user/{task_id}")
        assert r.status_code == 200
        assert r.json()["id"] == task_id
        assert r.json()["title"] == "Replace filter"

    def test_get_task_not_found(self, client):
        r = client.get("/tasks/user-123/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

    def test_update_task(self, client):
        created = client.post("/tasks", json={
            "user_id": "upd-user",
            "title": "Paint fence",
            "category": "yard",
        }).json()
        task_id = created["id"]

        r = client.put(f"/tasks/upd-user/{task_id}", json={"status": "done"})
        assert r.status_code == 200
        assert r.json()["status"] == "done"

    def test_delete_task(self, client):
        created = client.post("/tasks", json={
            "user_id": "del-user",
            "title": "Clean gutters",
            "category": "maintenance",
        }).json()
        task_id = created["id"]

        r = client.delete(f"/tasks/del-user/{task_id}")
        assert r.status_code == 204

        r2 = client.get(f"/tasks/del-user/{task_id}")
        assert r2.status_code == 404

    def test_task_status_values(self, client):
        for status_val in ("open", "in_progress", "done"):
            r = client.post("/tasks", json={
                "user_id": "status-user",
                "title": f"Task {status_val}",
                "category": "test",
                "status": status_val,
            })
            assert r.status_code == 201
            assert r.json()["status"] == status_val


# ---------------------------------------------------------------------------
# Goals CRUD
# ---------------------------------------------------------------------------

class TestGoals:
    def test_list_goals_empty(self, client):
        r = client.get("/goals/no-such-user")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_goal(self, client):
        r = client.post("/goals", json={
            "user_id": "goal-user",
            "title": "Renovate kitchen",
            "category": "renovation",
            "target_value": 15000,
            "target_unit": "USD",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == "Renovate kitchen"
        assert data["category"] == "renovation"
        assert data["is_active"] is True
        assert 0 <= data["progress_percentage"] <= 100
        assert "id" in data

    def test_list_goals_after_create(self, client):
        client.post("/goals", json={
            "user_id": "glist-user",
            "title": "Build deck",
            "category": "outdoor",
        })
        r = client.get("/goals/glist-user")
        assert r.status_code == 200
        goals = r.json()
        assert isinstance(goals, list)
        assert any(g["title"] == "Build deck" for g in goals)

    def test_get_goal_by_id(self, client):
        created = client.post("/goals", json={
            "user_id": "gget-user",
            "title": "New roof",
            "category": "structural",
        }).json()
        goal_id = created["id"]

        r = client.get(f"/goals/gget-user/{goal_id}")
        assert r.status_code == 200
        assert r.json()["id"] == goal_id

    def test_goal_progress_in_range(self, client):
        r = client.post("/goals", json={
            "user_id": "gprog-user",
            "title": "Paint all rooms",
            "category": "interior",
            "progress_percentage": 50,
        })
        assert r.status_code == 201
        assert 0 <= r.json()["progress_percentage"] <= 100

    def test_create_goal_missing_required(self, client):
        r = client.post("/goals", json={"user_id": "user-123"})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Assets CRUD
# ---------------------------------------------------------------------------

class TestAssets:
    def test_list_assets_empty(self, client):
        r = client.get("/assets/no-such-user")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_asset(self, client):
        r = client.post("/assets", json={
            "user_id": "asset-user",
            "name": "Lawn mower",
            "asset_type": "tool",
            "category": "yard_equipment",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Lawn mower"
        assert data["asset_type"] == "tool"
        assert "id" in data

    def test_list_assets_after_create(self, client):
        client.post("/assets", json={
            "user_id": "alist-user",
            "name": "Pressure washer",
            "asset_type": "tool",
            "category": "cleaning",
        })
        r = client.get("/assets/alist-user")
        assert r.status_code == 200
        assets = r.json()
        assert isinstance(assets, list)
        assert any(a["name"] == "Pressure washer" for a in assets)

    def test_filter_assets_by_type(self, client):
        for atype in ("tool", "appliance"):
            client.post("/assets", json={
                "user_id": "afilter-user",
                "name": f"Test {atype}",
                "asset_type": atype,
                "category": "test",
            })
        r = client.get("/assets/afilter-user?asset_type=tool")
        assert r.status_code == 200
        assets = r.json()
        assert all(a["asset_type"] == "tool" for a in assets)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_404_response_structure(self, client):
        r = client.get("/tasks/user-123/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404
        data = r.json()
        assert "error" in data
        assert "timestamp" in data
        assert "correlation_id" in data

    def test_invalid_route(self, client):
        r = client.get("/nonexistent/route")
        assert r.status_code == 404
