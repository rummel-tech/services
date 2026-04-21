"""Tests for audit logging in the Artemis Auth service."""
import os

# Set env vars before any imports to ensure settings picks them up
os.environ["DATABASE_URL"] = "sqlite:///test_audit.db"
os.environ["REDIS_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "development"
os.environ["DISABLE_AUTH"] = "true"

import pytest
from fastapi.testclient import TestClient

from auth.api.main import app
from auth.core.database import get_cursor, get_db

TEST_DB = "test_audit.db"


@pytest.fixture(scope="module")
def client():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    with TestClient(app) as c:
        yield c
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def _query_audit_logs(event: str) -> list:
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            "SELECT * FROM audit_logs WHERE event = ? ORDER BY created_at DESC",
            (event,),
        )
        return [dict(r) for r in cur.fetchall()]


def test_register_creates_audit_log(client):
    """Registering a new user writes a 'register' audit log entry."""
    email = "audit_register@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Audit Register"},
    )
    assert r.status_code == 201

    logs = _query_audit_logs("register")
    assert any(True for _ in logs), "Expected at least one 'register' audit log entry"


def test_login_success_creates_audit_log(client):
    """A successful login writes a 'login_success' audit log entry."""
    email = "audit_login_ok@example.com"
    password = "testpass123"

    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201

    user_id = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {r.json()['access_token']}"},
    ).json()["id"]

    r2 = client.post("/auth/login", json={"email": email, "password": password})
    assert r2.status_code == 200

    logs = _query_audit_logs("login_success")
    matching = [l for l in logs if l.get("user_id") == user_id]
    assert matching, f"Expected a 'login_success' entry for user {user_id}"


def test_login_failure_creates_audit_log(client):
    """A failed login attempt writes a 'login_failed' audit log entry."""
    email = "audit_login_fail@example.com"
    client.post("/auth/register", json={"email": email, "password": "correctpass"})

    r = client.post("/auth/login", json={"email": email, "password": "wrongpass"})
    assert r.status_code == 401

    logs = _query_audit_logs("login_failed")
    assert logs, "Expected at least one 'login_failed' audit log entry"
    import json
    metadata_values = [json.loads(l["metadata"]) if isinstance(l["metadata"], str) else l["metadata"] for l in logs]
    assert any(m.get("reason") == "invalid_credentials" for m in metadata_values)


def test_gdpr_export_creates_audit_log(client):
    """Calling GET /auth/me/data writes a 'gdpr_export' audit log entry."""
    email = "audit_gdpr_export@example.com"
    r = client.post("/auth/register", json={"email": email, "password": "testpass123"})
    assert r.status_code == 201
    token = r.json()["access_token"]
    user_id = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["id"]

    r2 = client.get("/auth/me/data", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200

    logs = _query_audit_logs("gdpr_export")
    matching = [l for l in logs if l.get("user_id") == user_id]
    assert matching, f"Expected a 'gdpr_export' entry for user {user_id}"


def test_audit_log_endpoint_admin_only(client):
    """GET /auth/audit-log returns 403 for non-admin users."""
    email = "audit_nonadmin@example.com"
    r = client.post("/auth/register", json={"email": email, "password": "testpass123"})
    assert r.status_code == 201
    token = r.json()["access_token"]

    r2 = client.get("/auth/audit-log", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 403
    body = r2.json()
    msg = body.get("detail") or body.get("error", {}).get("message", "")
    assert "Admin" in msg or "admin" in msg
