"""Tests for content-planner health check endpoints."""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DB = os.path.join(tempfile.gettempdir(), "content_health_test.db")

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


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "healthy")


def test_liveness(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


def test_readiness(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "checks" in data
    assert data["checks"]["database"]["ok"] is True
