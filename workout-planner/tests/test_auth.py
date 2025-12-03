import os
import sys
import tempfile
import pytest
import sqlite3
from fastapi.testclient import TestClient


# Counter for unique registration codes
_code_counter = 0


def _create_test_registration_code(db_path: str, code: str) -> None:
    """Create a registration code in the test database."""
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT OR IGNORE INTO registration_codes (code, is_used) VALUES (?, 0)", (code,))
    conn.commit()
    conn.close()


def _get_next_code() -> str:
    """Get the next unique test registration code."""
    global _code_counter
    code = f"TESTCODE{_code_counter:02d}"
    _code_counter += 1
    return code


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

    # Clear cached settings and reload database module to pick up new DATABASE_URL
    from settings import get_settings
    get_settings.cache_clear()

    # Force reload of database module to use new DATABASE_URL
    import importlib
    if 'database' in sys.modules:
        del sys.modules['database']

    import database  # type: ignore
    importlib.reload(database)
    database.init_sqlite()

    # Create test registration codes
    for i in range(50):  # Create enough codes for all tests
        _create_test_registration_code(tmp_db, f"TESTCODE{i:02d}")

    from main import app  # type: ignore
    return TestClient(app)


def test_register_success(client):
    code = _get_next_code()
    r = client.post("/auth/register", json={
        "email": "user1@example.com",
        "password": "Password123!",
        "registration_code": code
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data.get("status") == "registered"
    assert "access_token" in data and "refresh_token" in data


def test_register_duplicate_email(client):
    code1 = _get_next_code()
    code2 = _get_next_code()
    r1 = client.post("/auth/register", json={
        "email": "dupe@example.com",
        "password": "Password123!",
        "registration_code": code1
    })
    assert r1.status_code == 201
    r2 = client.post("/auth/register", json={
        "email": "dupe@example.com",
        "password": "OtherPass123!",
        "registration_code": code2
    })
    assert r2.status_code == 400
    assert "Email already registered" in r2.text


def test_register_weak_password(client):
    code = _get_next_code()
    r = client.post("/auth/register", json={
        "email": "weak@example.com",
        "password": "short",
        "registration_code": code
    })
    assert r.status_code == 422  # Pydantic validation error
    data = r.json()
    # Check the error details contain the password validation message
    details = data.get("error", {}).get("details", [])
    assert any("Password must be at least 8 characters" in str(detail) for detail in details)


def test_register_too_long_password(client):
    code = _get_next_code()
    long_pw = "A" * 73  # 73 ASCII chars => 73 bytes > 72 bcrypt limit
    r = client.post("/auth/register", json={
        "email": "toolong@example.com",
        "password": long_pw,
        "registration_code": code
    })
    assert r.status_code == 422
    data = r.json()
    # Check the error details contain the password validation message
    details = data.get("error", {}).get("details", [])
    assert any("Password must be at most 72 bytes" in str(detail) for detail in details)


def test_register_without_code_adds_to_waitlist(client):
    """Test that registration without a code adds user to waitlist."""
    r = client.post("/auth/register", json={
        "email": "nowaitlist@example.com",
        "password": "Password123!"
    })
    assert r.status_code == 201
    data = r.json()
    assert data.get("status") == "waitlisted"


def test_login_success(client):
    code = _get_next_code()
    client.post("/auth/register", json={
        "email": "login@example.com",
        "password": "Password123!",
        "registration_code": code
    })
    r = client.post("/auth/login", json={"email": "login@example.com", "password": "Password123!"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data


def test_login_bad_password(client):
    code = _get_next_code()
    client.post("/auth/register", json={
        "email": "badpass@example.com",
        "password": "Password123!",
        "registration_code": code
    })
    r = client.post("/auth/login", json={"email": "badpass@example.com", "password": "WrongPass"})
    assert r.status_code == 401
    assert "Incorrect email or password" in r.text


def test_login_nonexistent_email(client):
    r = client.post("/auth/login", json={"email": "nouser@example.com", "password": "Password123!"})
    assert r.status_code == 401
    assert "Incorrect email or password" in r.text


def test_refresh_and_me(client):
    code = _get_next_code()
    reg = client.post("/auth/register", json={
        "email": "refresh@example.com",
        "password": "Password123!",
        "registration_code": code
    })
    data = reg.json()
    access = data["access_token"]
    refresh = data["refresh_token"]

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
    code = _get_next_code()
    reg = client.post("/auth/register", json={
        "email": "logout@example.com",
        "password": "Password123!",
        "registration_code": code
    })
    access = reg.json()["access_token"]
    out = client.post("/auth/logout", headers={"Authorization": f"Bearer {access}"})
    assert out.status_code == 200
    assert out.json()["message"] == "Successfully logged out"
