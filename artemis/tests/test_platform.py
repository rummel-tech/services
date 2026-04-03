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
    assert data["status"] == "ok"
    assert data["service"] == "artemis"


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


def test_dashboard_briefing_requires_auth(client):
    r = client.get("/dashboard/briefing")
    assert r.status_code == 401


def test_dashboard_calendar_requires_auth(client):
    r = client.get("/dashboard/calendar")
    assert r.status_code == 401


def test_dashboard_widgets_requires_auth(client):
    r = client.get("/dashboard/widgets")
    assert r.status_code == 401


def test_dashboard_quick_actions_requires_auth(client):
    r = client.get("/dashboard/quick-actions")
    assert r.status_code == 401


def test_agent_tools_requires_auth(client):
    r = client.get("/agent/tools")
    assert r.status_code == 401


# ---- invalid token forms ----

def test_malformed_token(client):
    r = client.get("/modules", headers={"Authorization": "Bearer not.a.valid.jwt"})
    # dev fallback: jose will raise JWTError → 401
    assert r.status_code == 401


def test_missing_bearer_prefix(client):
    r = client.get("/modules", headers={"Authorization": "not-a-bearer-token"})
    assert r.status_code == 401


# ---- with a dev (unverified) token ----
# In dev mode with no auth service, tokens are decoded without signature verification.

def _make_dev_token(modules=None) -> str:
    """Create an unsigned JWT that works in dev mode (no sig verification)."""
    import base64
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload_data = json.dumps({
        "sub": "user-test-123",
        "email": "test@example.com",
        "name": "Test User",
        "iss": "artemis-auth",
        "modules": modules if modules is not None else ["workout-planner"],
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


def test_modules_list_contains_known_modules(client):
    """Modules from modules.yaml are registered even if unhealthy."""
    token = _make_dev_token()
    r = client.get("/modules", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()]
    assert "workout-planner" in ids
    assert "meal-planner" in ids
    assert "home-manager" in ids


def test_modules_list_structure(client):
    """Each entry in the modules list has the expected fields."""
    token = _make_dev_token()
    r = client.get("/modules", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    for m in r.json():
        assert "id" in m
        assert "healthy" in m
        assert "enabled" in m
        assert "last_checked" in m
        assert "error" in m


def test_modules_all_unhealthy(client):
    """Without running backends all modules report unhealthy."""
    token = _make_dev_token()
    r = client.get("/modules", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    for m in r.json():
        assert m["healthy"] is False


def test_module_get_unhealthy(client):
    """Can fetch details of an unhealthy but registered module."""
    token = _make_dev_token()
    r = client.get("/modules/workout-planner", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "workout-planner"
    assert data["healthy"] is False
    assert data["error"] is not None


def test_module_manifest_unavailable(client):
    """Requesting manifest of a registered but unhealthy module → 503."""
    token = _make_dev_token()
    r = client.get("/modules/workout-planner/manifest", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 503


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


def test_dashboard_user_fields(client):
    """Dashboard response includes user info derived from the token."""
    token = _make_dev_token()
    r = client.get("/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    user = r.json()["user"]
    assert user["id"] == "user-test-123"
    assert user["email"] == "test@example.com"
    assert user["name"] == "Test User"


def test_dashboard_modules_field(client):
    """Dashboard response lists all registered modules with health status."""
    token = _make_dev_token()
    r = client.get("/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    modules_map = r.json()["modules"]
    assert isinstance(modules_map, dict)
    assert "workout-planner" in modules_map
    assert "healthy" in modules_map["workout-planner"]


def test_dashboard_widgets_list_empty(client):
    """No healthy modules → empty widgets list."""
    token = _make_dev_token()
    r = client.get("/dashboard/widgets", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == []


def test_dashboard_briefing_empty(client):
    """No modules with /artemis/summary → empty summaries."""
    token = _make_dev_token()
    r = client.get("/dashboard/briefing", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert "summaries" in data
    assert data["summaries"] == []
    assert data["modules_included"] == 0


def test_dashboard_calendar_empty(client):
    """No modules with /artemis/calendar → empty events."""
    token = _make_dev_token()
    r = client.get("/dashboard/calendar", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert "events" in data
    assert data["events"] == []
    assert data["window_days"] == 14


def test_dashboard_quick_actions(client):
    token = _make_dev_token()
    r = client.get("/dashboard/quick-actions", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


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


def test_agent_chat_response_structure(client):
    """Agent chat response always has 'response' and 'tool_calls' fields."""
    token = _make_dev_token()
    r = client.post(
        "/agent/chat",
        json={"message": "Hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "response" in data
    assert "tool_calls" in data
    assert isinstance(data["tool_calls"], list)


def test_agent_chat_with_history(client):
    """Agent chat accepts optional conversation history."""
    token = _make_dev_token()
    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello! How can I help?"},
    ]
    r = client.post(
        "/agent/chat",
        json={"message": "What can you do?", "history": history},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert "response" in r.json()


def test_module_not_found(client):
    token = _make_dev_token()
    r = client.get("/modules/nonexistent-module", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_module_manifest_not_found(client):
    """Manifest endpoint for a completely unknown module → 404."""
    token = _make_dev_token()
    r = client.get("/modules/nonexistent-module/manifest", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_dashboard_with_all_modules_token(client):
    """Token with empty modules list means all modules are visible."""
    token = _make_dev_token(modules=[])
    r = client.get("/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert "widgets" in data
    # All modules in the map (even if unhealthy)
    assert len(data["modules"]) > 0


def test_dashboard_briefing_user_fields(client):
    """Briefing response includes user info derived from the token."""
    token = _make_dev_token()
    r = client.get("/dashboard/briefing", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    user = r.json()["user"]
    assert user["id"] == "user-test-123"
    assert user["name"] == "Test User"


def test_dashboard_calendar_user_fields(client):
    """Calendar response includes user info derived from the token."""
    token = _make_dev_token()
    r = client.get("/dashboard/calendar", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    user = r.json()["user"]
    assert user["id"] == "user-test-123"
