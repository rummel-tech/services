import os
import sys
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Ensure path includes server root
    test_file = os.path.abspath(__file__)
    server_root = os.path.dirname(os.path.dirname(test_file))
    if server_root not in sys.path:
        sys.path.insert(0, server_root)

    # Isolated sqlite DB
    tmp_db = os.path.join(tempfile.gettempdir(), "auth_test.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_db}"
    from database import init_sqlite  # type: ignore
    init_sqlite()
    from main import app  # type: ignore
    return TestClient(app)


def test_register_success(client):
    r = client.post("/auth/register", json={"email": "user1@example.com", "password": "Password123!"})
    assert r.status_code == 201, r.text
    data = r.json()
    assert "access_token" in data and "refresh_token" in data


def test_register_duplicate_email(client):
    r1 = client.post("/auth/register", json={"email": "dupe@example.com", "password": "Password123!"})
    assert r1.status_code == 201
    r2 = client.post("/auth/register", json={"email": "dupe@example.com", "password": "OtherPass123!"})
    assert r2.status_code == 400
    assert "Email already registered" in r2.text


def test_register_weak_password(client):
    r = client.post("/auth/register", json={"email": "weak@example.com", "password": "short"})
    assert r.status_code == 422  # Pydantic validation error
    data = r.json()
    # Check the error details contain the password validation message
    details = data.get("error", {}).get("details", [])
    assert any("Password must be at least 8 characters" in str(detail) for detail in details)


def test_register_too_long_password(client):
    long_pw = "A" * 73  # 73 ASCII chars => 73 bytes > 72 bcrypt limit
    r = client.post("/auth/register", json={"email": "toolong@example.com", "password": long_pw})
    assert r.status_code == 422
    data = r.json()
    # Check the error details contain the password validation message
    details = data.get("error", {}).get("details", [])
    assert any("Password must be at most 72 bytes" in str(detail) for detail in details)


def test_login_success(client):
    client.post("/auth/register", json={"email": "login@example.com", "password": "Password123!"})
    r = client.post("/auth/login", json={"email": "login@example.com", "password": "Password123!"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data


def test_login_bad_password(client):
    client.post("/auth/register", json={"email": "badpass@example.com", "password": "Password123!"})
    r = client.post("/auth/login", json={"email": "badpass@example.com", "password": "WrongPass"})
    assert r.status_code == 401
    assert "Incorrect email or password" in r.text


def test_login_nonexistent_email(client):
    r = client.post("/auth/login", json={"email": "nouser@example.com", "password": "Password123!"})
    assert r.status_code == 401
    assert "Incorrect email or password" in r.text


def test_refresh_and_me(client):
    reg = client.post("/auth/register", json={"email": "refresh@example.com", "password": "Password123!"})
    access = reg.json()["access_token"]
    refresh = reg.json()["refresh_token"]

    # /auth/me
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["email"] == "refresh@example.com"

    # refresh endpoint
    ref = client.post("/auth/refresh", headers={"Authorization": f"Bearer {refresh}"})
    assert ref.status_code == 200
    new_tokens = ref.json()
    assert new_tokens["access_token"] != access


def test_logout(client):
    reg = client.post("/auth/register", json={"email": "logout@example.com", "password": "Password123!"})
    access = reg.json()["access_token"]
    out = client.post("/auth/logout", headers={"Authorization": f"Bearer {access}"})
    assert out.status_code == 200
    assert out.json()["message"] == "Successfully logged out"