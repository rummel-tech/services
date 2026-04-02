"""Tests for content-planner pillars and sources endpoints."""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DB = os.path.join(tempfile.gettempdir(), "content_pillars_test.db")

os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["REDIS_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "development"
os.environ["DISABLE_AUTH"] = "true"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="module")
def client():
    if os.path.exists(_DB):
        os.remove(_DB)
    from main import app  # noqa: PLC0415
    from routers.auth import require_token  # noqa: PLC0415

    async def _mock_auth():
        return {"user_id": "dev-user", "sub": "dev-user", "email": "dev@local"}

    app.dependency_overrides[require_token] = _mock_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Pillars tests
# ---------------------------------------------------------------------------

def test_list_pillars_empty(client):
    r = client.get("/pillars", headers=_AUTH)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_pillar(client):
    r = client.post("/pillars", headers=_AUTH, json={
        "name": "Stoicism",
        "color": 4280391411,
        "priority_weight": 1.5,
        "is_quarterly_focus": True,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Stoicism"
    assert data["is_quarterly_focus"] is True
    assert "id" in data


def test_create_pillar_missing_name(client):
    r = client.post("/pillars", headers=_AUTH, json={"color": 1234})
    assert r.status_code == 422


def test_get_pillar(client):
    r = client.post("/pillars", headers=_AUTH, json={
        "name": "Leadership",
        "color": 4294944000,
        "priority_weight": 1.0,
        "is_quarterly_focus": False,
    })
    pillar_id = r.json()["id"]

    r = client.get(f"/pillars/{pillar_id}", headers=_AUTH)
    assert r.status_code == 200
    assert r.json()["name"] == "Leadership"


def test_get_pillar_not_found(client):
    r = client.get("/pillars/nonexistent-id", headers=_AUTH)
    assert r.status_code == 404


def test_update_pillar(client):
    r = client.post("/pillars", headers=_AUTH, json={
        "name": "To Update",
        "color": 1234,
        "priority_weight": 1.0,
        "is_quarterly_focus": False,
    })
    pillar_id = r.json()["id"]

    r = client.patch(f"/pillars/{pillar_id}", headers=_AUTH, json={
        "name": "Updated Pillar",
        "priority_weight": 2.0,
    })
    assert r.status_code == 200
    assert r.json()["name"] == "Updated Pillar"


def test_update_pillar_no_fields(client):
    r = client.post("/pillars", headers=_AUTH, json={
        "name": "No Update",
        "color": 1234,
        "priority_weight": 1.0,
        "is_quarterly_focus": False,
    })
    pillar_id = r.json()["id"]
    r = client.patch(f"/pillars/{pillar_id}", headers=_AUTH, json={})
    assert r.status_code == 400


def test_update_pillar_not_found(client):
    r = client.patch("/pillars/nonexistent-id", headers=_AUTH, json={"name": "Ghost"})
    assert r.status_code == 404


def test_delete_pillar(client):
    r = client.post("/pillars", headers=_AUTH, json={
        "name": "To Delete",
        "color": 1234,
        "priority_weight": 1.0,
        "is_quarterly_focus": False,
    })
    pillar_id = r.json()["id"]

    r = client.delete(f"/pillars/{pillar_id}", headers=_AUTH)
    assert r.status_code == 204

    r = client.get(f"/pillars/{pillar_id}", headers=_AUTH)
    assert r.status_code == 404


def test_delete_pillar_not_found(client):
    r = client.delete("/pillars/nonexistent-id", headers=_AUTH)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Sources tests
# ---------------------------------------------------------------------------

def test_list_sources_empty(client):
    r = client.get("/sources", headers=_AUTH)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_source(client):
    r = client.post("/sources", headers=_AUTH, json={
        "title": "The Tim Ferriss Show",
        "url": "https://tim.blog/podcast",
        "type": "podcast",
        "trust_level": "high",
        "blocked": False,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "The Tim Ferriss Show"
    assert data["trust_level"] == "high"
    assert data["blocked"] is False


def test_create_source_missing_title(client):
    r = client.post("/sources", headers=_AUTH, json={"type": "podcast"})
    assert r.status_code == 422


def test_get_source(client):
    r = client.post("/sources", headers=_AUTH, json={
        "title": "Lex Fridman Podcast",
        "type": "podcast",
        "trust_level": "neutral",
        "blocked": False,
    })
    source_id = r.json()["id"]

    r = client.get(f"/sources/{source_id}", headers=_AUTH)
    assert r.status_code == 200
    assert r.json()["title"] == "Lex Fridman Podcast"


def test_get_source_not_found(client):
    r = client.get("/sources/nonexistent-id", headers=_AUTH)
    assert r.status_code == 404


def test_update_source(client):
    r = client.post("/sources", headers=_AUTH, json={
        "title": "Source to Update",
        "type": "article",
        "trust_level": "neutral",
        "blocked": False,
    })
    source_id = r.json()["id"]

    r = client.patch(f"/sources/{source_id}", headers=_AUTH, json={
        "trust_level": "high",
        "blocked": True,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["trust_level"] == "high"
    assert data["blocked"] is True


def test_update_source_not_found(client):
    r = client.patch("/sources/nonexistent-id", headers=_AUTH, json={"title": "Ghost"})
    assert r.status_code == 404


def test_delete_source(client):
    r = client.post("/sources", headers=_AUTH, json={
        "title": "To Delete Source",
        "type": "video",
        "trust_level": "low",
        "blocked": False,
    })
    source_id = r.json()["id"]

    r = client.delete(f"/sources/{source_id}", headers=_AUTH)
    assert r.status_code == 204

    r = client.get(f"/sources/{source_id}", headers=_AUTH)
    assert r.status_code == 404


def test_delete_source_not_found(client):
    r = client.delete("/sources/nonexistent-id", headers=_AUTH)
    assert r.status_code == 404
