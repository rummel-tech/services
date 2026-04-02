"""Tests for content-planner content_items and queue endpoints."""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DB = os.path.join(tempfile.gettempdir(), "content_items_test.db")

os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["REDIS_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "development"
os.environ["DISABLE_AUTH"] = "true"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="module")
def client():
    from main import app  # noqa: PLC0415
    from routers.auth import require_token  # noqa: PLC0415

    async def _mock_auth():
        return {"user_id": "dev-user", "sub": "dev-user", "email": "dev@local"}

    app.dependency_overrides[require_token] = _mock_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def item_id(client):
    r = client.post("/content", headers=_AUTH, json={
        "title": "Fixture Item",
        "type": "episode",
        "duration_ms": 3600000,
        "mode": "tactical",
        "status": "inbox",
    })
    assert r.status_code == 201
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Content Items tests
# ---------------------------------------------------------------------------

def test_list_content_items_empty(client):
    r = client.get("/content", headers=_AUTH)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_content_item(client):
    r = client.post("/content", headers=_AUTH, json={
        "title": "How to Build Habits",
        "type": "episode",
        "duration_ms": 2700000,
        "mode": "tactical",
        "status": "inbox",
        "topics": ["habits", "productivity"],
    })
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "How to Build Habits"
    assert data["type"] == "episode"
    assert data["topics"] == ["habits", "productivity"]
    assert "id" in data


def test_create_content_item_missing_title(client):
    r = client.post("/content", headers=_AUTH, json={"type": "episode"})
    assert r.status_code == 422


def test_get_content_item(client, item_id):
    r = client.get(f"/content/{item_id}", headers=_AUTH)
    assert r.status_code == 200
    assert r.json()["id"] == item_id


def test_get_content_item_not_found(client):
    r = client.get("/content/nonexistent-id", headers=_AUTH)
    assert r.status_code == 404


def test_update_content_item(client, item_id):
    r = client.patch(f"/content/{item_id}", headers=_AUTH, json={"status": "queued"})
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


def test_update_content_item_no_fields(client, item_id):
    r = client.patch(f"/content/{item_id}", headers=_AUTH, json={})
    assert r.status_code == 400


def test_update_content_item_not_found(client):
    r = client.patch("/content/nonexistent-id", headers=_AUTH, json={"status": "queued"})
    assert r.status_code == 404


def test_update_play_position(client, item_id):
    r = client.post(f"/content/{item_id}/play-position?position_ms=30000", headers=_AUTH)
    assert r.status_code == 200
    assert r.json()["play_state"]["position_ms"] == 30000


def test_record_skip(client, item_id):
    r = client.post(f"/content/{item_id}/skip", headers=_AUTH)
    assert r.status_code == 200
    assert r.json()["feedback"]["skip_count"] >= 1


def test_flag_redundant(client, item_id):
    r = client.post(f"/content/{item_id}/flag-redundant", headers=_AUTH)
    assert r.status_code == 200
    assert r.json()["feedback"]["redundant_flag"] is True


def test_mark_completed(client):
    r = client.post("/content", headers=_AUTH, json={
        "title": "To Complete",
        "type": "article",
        "duration_ms": 1200000,
        "mode": "deep",
        "status": "inbox",
    })
    new_id = r.json()["id"]
    r = client.post(f"/content/{new_id}/complete", headers=_AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_delete_content_item(client):
    r = client.post("/content", headers=_AUTH, json={
        "title": "To Delete",
        "type": "episode",
        "duration_ms": 600000,
        "mode": "recovery",
        "status": "inbox",
    })
    del_id = r.json()["id"]

    r = client.delete(f"/content/{del_id}", headers=_AUTH)
    assert r.status_code == 204

    r = client.get(f"/content/{del_id}", headers=_AUTH)
    assert r.status_code == 404


def test_delete_content_item_not_found(client):
    r = client.delete("/content/nonexistent-id", headers=_AUTH)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Queue tests
# ---------------------------------------------------------------------------

def test_get_queue_empty(client):
    r = client.get("/queue", headers=_AUTH)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_queue_stats(client):
    r = client.get("/queue/stats", headers=_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "total_cap" in data
    assert "by_pillar" in data
    assert "by_mode" in data


def test_enqueue_item(client):
    r = client.post("/content", headers=_AUTH, json={
        "title": "Queue Test Item",
        "type": "episode",
        "duration_ms": 1800000,
        "mode": "tactical",
        "status": "inbox",
    })
    new_id = r.json()["id"]

    r = client.post(f"/queue/{new_id}/enqueue", headers=_AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


def test_dequeue_item(client):
    r = client.post("/content", headers=_AUTH, json={
        "title": "Dequeue Test Item",
        "type": "episode",
        "duration_ms": 900000,
        "mode": "recovery",
        "status": "inbox",
    })
    new_id = r.json()["id"]
    client.post(f"/queue/{new_id}/enqueue", headers=_AUTH)

    r = client.post(f"/queue/{new_id}/dequeue", headers=_AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "inbox"


def test_next_in_queue_empty(client):
    r = client.get("/queue/next", headers=_AUTH)
    assert r.status_code in (200, 404)


def test_reorder_queue(client):
    r1 = client.post("/content", headers=_AUTH, json={"title": "Q1", "type": "episode", "duration_ms": 100, "mode": "tactical", "status": "inbox"})
    r2 = client.post("/content", headers=_AUTH, json={"title": "Q2", "type": "episode", "duration_ms": 100, "mode": "tactical", "status": "inbox"})
    id1 = r1.json()["id"]
    id2 = r2.json()["id"]
    client.post(f"/queue/{id1}/enqueue", headers=_AUTH)
    client.post(f"/queue/{id2}/enqueue", headers=_AUTH)

    r = client.post("/queue/reorder", headers=_AUTH, json={"item_ids": [id2, id1]})
    assert r.status_code == 204
