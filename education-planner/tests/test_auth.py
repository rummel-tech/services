"""Tests for education-planner auth endpoints."""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DB = os.path.join(tempfile.gettempdir(), "edu_auth_test.db")

os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["REDIS_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "development"
os.environ["DISABLE_AUTH"] = "false"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_REG_CODE = "EDUCODE1"


@pytest.fixture(scope="module")
def client():
    from main import app  # noqa: PLC0415
    import core.database as _dbmod  # noqa: PLC0415
    db_path = _dbmod.DATABASE_URL.replace("sqlite:///", "")
    if os.path.exists(db_path):
        os.remove(db_path)
    _dbmod._sqlite_initialized = False
    from core.database import get_db, get_cursor  # noqa: PLC0415
    with TestClient(app) as c:
        with get_db() as conn:
            cur = get_cursor(conn)
            cur.execute(
                "INSERT OR IGNORE INTO registration_codes (code, is_used) VALUES (?, 0)",
                (_REG_CODE,),
            )
            conn.commit()
        yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    r = client.post("/auth/register", json={
        "email": "edu_authtest@example.com",
        "password": "Password123!",
        "registration_code": _REG_CODE,
    })
    assert r.status_code == 201
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_validate_code_valid(client):
    from core.database import get_db, get_cursor  # noqa: PLC0415
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("INSERT OR IGNORE INTO registration_codes (code, is_used) VALUES ('EDUVALID', 0)")
        conn.commit()
    r = client.post("/auth/validate-code?code=EDUVALID")
    assert r.status_code == 200
    assert r.json()["valid"] is True


def test_validate_code_invalid(client):
    r = client.post("/auth/validate-code?code=BADBADXX")
    assert r.status_code == 200
    assert r.json()["valid"] is False


def test_register_without_code_goes_to_waitlist(client):
    r = client.post("/auth/register", json={
        "email": "edu_waitlist@example.com",
        "password": "Password123!",
    })
    assert r.status_code == 201
    assert r.json()["status"] == "waitlisted"


def test_register_success(client):
    from core.database import get_db, get_cursor  # noqa: PLC0415
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute("INSERT OR IGNORE INTO registration_codes (code, is_used) VALUES ('EDUNEW1', 0)")
        conn.commit()
    r = client.post("/auth/register", json={
        "email": "edu_newuser@example.com",
        "password": "Password123!",
        "registration_code": "EDUNEW1",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "registered"
    assert "access_token" in data


def test_register_duplicate_email(client, auth_headers):
    r = client.post("/auth/register", json={
        "email": "edu_authtest@example.com",
        "password": "Password123!",
    })
    assert r.status_code == 400


def test_login_success(client, auth_headers):
    r = client.post("/auth/login", json={
        "email": "edu_authtest@example.com",
        "password": "Password123!",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_wrong_password(client):
    r = client.post("/auth/login", json={
        "email": "edu_authtest@example.com",
        "password": "WrongPassword!",
    })
    assert r.status_code == 401


def test_login_unknown_email(client):
    r = client.post("/auth/login", json={
        "email": "nobody@example.com",
        "password": "Password123!",
    })
    assert r.status_code == 401


def test_me(client, auth_headers):
    r = client.get("/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "edu_authtest@example.com"


def test_me_unauthenticated(client):
    r = client.get("/auth/me")
    assert r.status_code in (401, 404)


def test_logout(client, auth_headers):
    r = client.post("/auth/logout", headers=auth_headers)
    assert r.status_code == 200
    assert "logged out" in r.json()["message"].lower()
