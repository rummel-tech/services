"""Tests for the Artemis platform service.

These tests run without any real module services running — the registry
starts empty because modules.yaml points to unreachable localhost ports.
We test the platform's own behaviour: startup, auth, health, empty registry responses.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ["ENVIRONMENT"] = "development"
os.environ["REGISTRY_REFRESH_SECONDS"] = "0"  # no background refresh in tests

from artemis.api.main import app  # noqa: E402
from artemis.core.registry import registry  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ---- health / ready (no auth) ----

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert data["service"] == "artemis"
    assert "modules" in data


def test_ready(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


# ---- auth required ----

def test_modules_requires_auth(client):
    r = client.get("/modules")
    assert r.status_code == 401


def test_dashboard_requires_auth(client):
    r = client.get("/dashboard")
    assert r.status_code == 401


def test_agent_chat_requires_auth(client):
    r = client.post("/agent/chat", json={"message": "hello"})
    assert r.status_code == 401


# ---- with a dev (unverified) token ----
# In dev mode with no auth service, tokens are decoded without signature verification.

def _make_dev_token() -> str:
    """Create an unsigned JWT that works in dev mode (no sig verification)."""
    import base64
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload_data = json.dumps({
        "sub": "user-test-123",
        "email": "test@example.com",
        "name": "Test User",
        "iss": "artemis-auth",
        "modules": ["workout-planner"],
        "permissions": [],
    }).encode()
    payload = base64.urlsafe_b64encode(payload_data).rstrip(b"=").decode()
    return f"{header}.{payload}."


def test_modules_with_dev_token(client):
    token = _make_dev_token()
    r = client.get("/modules", headers={"Authorization": f"Bearer {token}"})
    # In dev mode with no auth service the token is accepted
    assert r.status_code == 200
    # All modules will be unhealthy since the backends aren't running
    modules = r.json()
    assert isinstance(modules, list)


def test_dashboard_with_dev_token_empty(client):
    token = _make_dev_token()
    r = client.get("/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert "widgets" in data
    assert "modules" in data
    assert "user" in data
    # No healthy modules → empty widgets list
    assert data["widgets"] == []


def test_agent_tools_list(client):
    token = _make_dev_token()
    r = client.get("/agent/tools", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # No healthy modules → no tools
    assert r.json() == []


def test_agent_chat_no_anthropic_key(client):
    """Without ANTHROPIC_API_KEY the agent returns a config error message."""
    token = _make_dev_token()
    r = client.post(
        "/agent/chat",
        json={"message": "What's my workout today?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "response" in data
    assert "ANTHROPIC_API_KEY" in data["response"]


def test_dashboard_quick_actions(client):
    token = _make_dev_token()
    r = client.get("/dashboard/quick-actions", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_module_not_found(client):
    token = _make_dev_token()
    r = client.get("/modules/nonexistent-module", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404
