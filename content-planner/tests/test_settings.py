"""Tests for content-planner user_settings endpoints."""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DB = os.path.join(tempfile.gettempdir(), "content_settings_test.db")

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


def test_get_settings_creates_defaults(client):
    r = client.get("/settings", headers=_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert "queue_caps" in data
    assert data["queue_caps"]["total_cap"] == 10
    assert "notifications" in data
    assert "context_mode_map" in data


def test_update_settings_queue_caps(client):
    r = client.patch("/settings", headers=_AUTH, json={
        "queue_caps": {"total_cap": 20, "per_pillar_cap": 8, "per_mode_cap": 7},
    })
    assert r.status_code == 200
    data = r.json()
    assert data["queue_caps"]["total_cap"] == 20
    assert data["queue_caps"]["per_pillar_cap"] == 8


def test_update_settings_notifications(client):
    r = client.patch("/settings", headers=_AUTH, json={
        "notifications": {
            "weekly_review_reminder": False,
            "queue_empty_alert": True,
            "inbox_overflow_alert": True,
            "inbox_overflow_threshold": 30,
        },
    })
    assert r.status_code == 200
    data = r.json()
    assert data["notifications"]["weekly_review_reminder"] is False
    assert data["notifications"]["inbox_overflow_threshold"] == 30


def test_update_settings_context_mode_map(client):
    r = client.patch("/settings", headers=_AUTH, json={
        "context_mode_map": {"commute": "deep", "workout": "tactical"},
    })
    assert r.status_code == 200
    data = r.json()
    assert data["context_mode_map"]["commute"] == "deep"


def test_update_settings_start_behavior(client):
    r = client.patch("/settings", headers=_AUTH, json={"start_behavior": "manual"})
    assert r.status_code == 200
    assert r.json()["start_behavior"] == "manual"


def test_get_settings_persists(client):
    r = client.get("/settings", headers=_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["start_behavior"] == "manual"
