"""Onboarding and auth flows aligned to requirements/test-plan."""
import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient

# Configure test env before importing app/settings
TEST_DB = "test_auth.db"
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DISABLE_AUTH", "true")  # bypass auth for admin endpoints in dev
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"

from core.database import init_sqlite, get_db, get_cursor
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db() -> Generator[None, None, None]:
    """Ensure a fresh SQLite database per test."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_sqlite()
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def _create_registration_code(code: str = "TESTCODE1") -> str:
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("INSERT INTO registration_codes (code) VALUES (?)", (code,))
        conn.commit()
    return code


def _create_expired_code(code: str = "EXPIRE1") -> str:
    with get_db() as conn:
        cur = get_cursor(conn)
        # Set expires_at in the past
        cur.execute(
            "INSERT INTO registration_codes (code, expires_at) VALUES (?, datetime('now', '-1 day'))",
            (code,)
        )
        conn.commit()
    return code


def test_waitlist_join_success():
    response = client.post("/waitlist", json={"email": "newuser@example.com"})
    assert response.status_code == 201
    assert "waitlist" in response.json()["message"].lower()


def test_waitlist_duplicate_rejected():
    client.post("/waitlist", json={"email": "dup@example.com"})
    response = client.post("/waitlist", json={"email": "dup@example.com"})
    assert response.status_code == 400
    assert "already" in response.json()["detail"].lower()


def test_register_without_code_adds_waitlist():
    response = client.post(
        "/auth/register",
        json={"email": "waitlist@example.com", "password": "password123"}
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "waitlisted"
    assert "waiting list" in payload["message"].lower()


def test_register_with_invalid_code_waitlists_user():
    response = client.post(
        "/auth/register",
        json={
            "email": "badcode@example.com",
            "password": "password123",
            "registration_code": "NOTREAL"
        }
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "waitlisted"
    assert "invalid" in payload["message"].lower()


def test_register_with_valid_code_creates_user_and_tokens():
    code = _create_registration_code("REALCODE")
    response = client.post(
        "/auth/register",
        json={
            "email": "member@example.com",
            "password": "password123",
            "registration_code": code,
            "full_name": "Member User"
        }
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "registered"
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["refresh_token"]


def test_admin_invite_from_waitlist_generates_code_and_removes_entry():
    email = "waitlist-invite@example.com"
    client.post("/waitlist", json={"email": email})

    response = client.post(
        "/auth/admin/waitlist/invite",
        params={"email": email, "expires_in_days": 7}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == email
    assert payload["code"]
    assert "removed" in payload["message"].lower()

    # Ensure waitlist entry is gone
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("SELECT * FROM waitlist WHERE email = ?", (email,))
        assert cur.fetchone() is None


def test_registration_code_single_use_enforced():
    code = _create_registration_code("SINGLEUSE")

    # First registration succeeds
    first = client.post(
        "/auth/register",
        json={"email": "one@example.com", "password": "password123", "registration_code": code}
    )
    assert first.status_code == 201
    assert first.json()["status"] == "registered"

    # Second registration with same code is rejected (waitlisted)
    second = client.post(
        "/auth/register",
        json={"email": "two@example.com", "password": "password123", "registration_code": code}
    )
    assert second.status_code == 201
    assert second.json()["status"] == "waitlisted"


def test_registration_with_expired_code_waitlists_user():
    code = _create_expired_code("EXPIRED1")
    response = client.post(
        "/auth/register",
        json={"email": "expired@example.com", "password": "password123", "registration_code": code}
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "waitlisted"
    assert "invalid" in payload["message"].lower()


def test_validate_code_endpoint_valid_and_invalid():
    valid_code = _create_registration_code("VALIDVAL")
    expired_code = _create_expired_code("OLDVAL")

    res_valid = client.post("/auth/validate-code", params={"code": valid_code})
    assert res_valid.status_code == 200
    assert res_valid.json()["valid"] is True

    res_invalid = client.post("/auth/validate-code", params={"code": "NOPE"})
    assert res_invalid.status_code == 200
    assert res_invalid.json()["valid"] is False

    res_expired = client.post("/auth/validate-code", params={"code": expired_code})
    assert res_expired.status_code == 200
    assert res_expired.json()["valid"] is False


def test_login_and_refresh_after_registration():
    code = _create_registration_code("LOGINCODE")
    register_response = client.post(
        "/auth/register",
        json={
            "email": "login@example.com",
            "password": "password123",
            "registration_code": code
        }
    )
    refresh_token = register_response.json()["refresh_token"]

    # Login again to validate credentials
    login_response = client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "password123"}
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    # Refresh token flow
    refresh_response = client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()
    assert refreshed["access_token"]
    assert refreshed["refresh_token"]

    # Logout with the active access token
    logout_response = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert logout_response.status_code == 200
