"""Tests for the Artemis Auth service."""
import os

# Set env vars before any imports to ensure settings picks them up
os.environ["DATABASE_URL"] = "sqlite:///test_auth.db"
os.environ["REDIS_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "development"
os.environ["DISABLE_AUTH"] = "true"

import pytest
from fastapi.testclient import TestClient

from auth.api.main import app

TEST_DB = "test_auth.db"


@pytest.fixture(scope="module")
def client():
    # Remove stale test DB before the module runs
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    with TestClient(app) as c:
        yield c
    # Cleanup after module
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_public_key(client):
    r = client.get("/auth/public-key")
    assert r.status_code == 200
    data = r.json()
    assert "public_key" in data
    assert data["algorithm"] == "RS256"
    assert "BEGIN PUBLIC KEY" in data["public_key"]


def test_register_and_login(client):
    email = "test@example.com"
    password = "password123"

    # Register
    r = client.post("/auth/register", json={"email": email, "password": password, "full_name": "Test User"})
    assert r.status_code == 201
    tokens = r.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    # Duplicate register
    r2 = client.post("/auth/register", json={"email": email, "password": password})
    assert r2.status_code == 400

    # Login
    r3 = client.post("/auth/login", json={"email": email, "password": password})
    assert r3.status_code == 200
    assert "access_token" in r3.json()


def test_me(client):
    email = "me_test@example.com"
    r = client.post("/auth/register", json={"email": email, "password": "testpass1"})
    assert r.status_code == 201
    token = r.json()["access_token"]

    r2 = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["email"] == email


def test_refresh(client):
    email = "refresh_test@example.com"
    r = client.post("/auth/register", json={"email": email, "password": "testpass1"})
    assert r.status_code == 201
    refresh_token = r.json()["refresh_token"]

    r2 = client.post("/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"})
    assert r2.status_code == 200
    assert "access_token" in r2.json()


def test_token_is_artemis_format(client):
    """Verify the JWT payload contains required Artemis fields."""
    from jose import jwt as jose_jwt
    from auth.core.jwt_service import get_public_key_pem

    email = "payload_test@example.com"
    r = client.post("/auth/register", json={"email": email, "password": "testpass1", "full_name": "Shawn"})
    assert r.status_code == 201
    token = r.json()["access_token"]

    pub = get_public_key_pem()
    payload = jose_jwt.decode(token, pub, algorithms=["RS256"], issuer="artemis-auth")

    assert payload["iss"] == "artemis-auth"
    assert payload["email"] == email
    assert "sub" in payload
    assert "modules" in payload
    assert "permissions" in payload
    assert "exp" in payload
    assert "jti" in payload


def test_wrong_password(client):
    email = "wrongpw@example.com"
    client.post("/auth/register", json={"email": email, "password": "correctpass"})
    r = client.post("/auth/login", json={"email": email, "password": "wrongpass"})
    assert r.status_code == 401


def test_logout(client):
    email = "logout_test@example.com"
    r = client.post("/auth/register", json={"email": email, "password": "testpass1"})
    token = r.json()["access_token"]

    r2 = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["message"] == "Logged out"


def test_gdpr_data_export(client):
    """GET /auth/me/data returns all personal data for the authenticated user."""
    email = "gdpr_export@example.com"
    r = client.post("/auth/register", json={"email": email, "password": "testpass1", "full_name": "GDPR User"})
    token = r.json()["access_token"]

    r2 = client.get("/auth/me/data", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    data = r2.json()
    assert data["user"]["email"] == email
    assert data["user"]["full_name"] == "GDPR User"
    assert "exported_at" in data
    assert "refresh_tokens" in data


def test_gdpr_delete_account(client):
    """DELETE /auth/me permanently removes the account (GDPR Art. 17)."""
    email = "gdpr_delete@example.com"
    r = client.post("/auth/register", json={"email": email, "password": "testpass1"})
    assert r.status_code == 201
    token = r.json()["access_token"]

    # Delete the account
    r2 = client.delete("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 204

    # Account should no longer exist — login must fail
    r3 = client.post("/auth/login", json={"email": email, "password": "testpass1"})
    assert r3.status_code == 401


def test_me_unauthenticated(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_register_weak_password(client):
    # Short passwords are caught by the route handler and return 400
    r = client.post("/auth/register", json={"email": "weak@example.com", "password": "short"})
    assert r.status_code == 400
