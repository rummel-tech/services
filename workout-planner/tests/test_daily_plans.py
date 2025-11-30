import os
import sys
import tempfile
from pathlib import Path
from datetime import date

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Ensure path includes server root so imports resolve
    test_file = Path(__file__).resolve()
    server_root = test_file.parents[1]  # python_fastapi_server directory
    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))

    # Isolated SQLite DB for these tests
    tmp_db = os.path.join(tempfile.gettempdir(), "daily_plans_test.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_db}"

    from database import init_sqlite  # type: ignore
    init_sqlite()
    from main import app  # type: ignore
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_data(client):
    """Get authentication token and user ID for testing"""
    response = client.post("/auth/register", json={"email": "testuser@example.com", "password": "TestPassword123!"})
    assert response.status_code == 201
    token = response.json()["access_token"]

    # Get user ID from /auth/me
    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    user_id = str(me_response.json()["id"])

    return {"token": token, "user_id": user_id}


@pytest.fixture(scope="module")
def auth_token(auth_data):
    """Get authentication token for testing"""
    return auth_data["token"]


@pytest.fixture(scope="module")
def user_id(auth_data):
    """Get user ID for testing"""
    return auth_data["user_id"]


def _plan_payload(user_id: str, d: str, warmup=None, main=None, cooldown=None, notes: str = "", status: str = "pending"):
    return {
        "user_id": user_id,
        "date": d,
        "plan_json": {
            "warmup": warmup or [],
            "main": main or [],
            "cooldown": cooldown or [],
            "notes": notes,
        },
        "status": status,
    }


def test_default_daily_plan(client, auth_token, user_id):
    today = str(date.today())
    r = client.get(f"/daily-plans/{user_id}/{today}", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["user_id"] == user_id
    assert data["warmup"] == []
    assert data["main"] == []
    assert data["cooldown"] == []
    assert data["notes"] == ""


def test_save_basic_daily_plan(client, auth_token, user_id):
    today = str(date.today())
    payload = _plan_payload(
        user_id,
        today,
        warmup=["5 min jog"],
        main=["3x10 squats", "3x10 push-ups"],
        cooldown=["stretch"],
        notes="Solid start",
    )
    headers = {"Authorization": f"Bearer {auth_token}"}
    put = client.put(f"/daily-plans/{user_id}/{today}", json=payload, headers=headers)
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["warmup"] == ["5 min jog"]
    assert len(body["main"]) == 2
    assert body["notes"] == "Solid start"

    get2 = client.get(f"/daily-plans/{user_id}/{today}", headers=headers)
    assert get2.status_code == 200
    again = get2.json()
    assert again["main"][1].startswith("3x10 push")


def test_append_line_to_existing_plan(client, auth_token, user_id):
    today = str(date.today())
    headers = {"Authorization": f"Bearer {auth_token}"}
    # Initial save
    first = _plan_payload(user_id, today, main=["A", "B"])
    client.put(f"/daily-plans/{user_id}/{today}", json=first, headers=headers)
    # Append new line C
    updated = _plan_payload(user_id, today, main=["A", "B", "C"], notes="Added C")
    put2 = client.put(f"/daily-plans/{user_id}/{today}", json=updated, headers=headers)
    assert put2.status_code == 200
    body = put2.json()
    assert body["main"] == ["A", "B", "C"]
    assert body["notes"] == "Added C"

    # Retrieve
    get3 = client.get(f"/daily-plans/{user_id}/{today}", headers=headers)
    assert get3.status_code == 200
    body2 = get3.json()
    assert body2["main"][-1] == "C"


def test_save_with_blank_line(client, auth_token, user_id):
    today = str(date.today())
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = _plan_payload(user_id, today, main=["First", "", "Second"], notes="Has blank")
    put = client.put(f"/daily-plans/{user_id}/{today}", json=payload, headers=headers)
    assert put.status_code == 200
    data = put.json()
    # Backend currently preserves blank entries
    assert data["main"] == ["First", "", "Second"]

    get2 = client.get(f"/daily-plans/{user_id}/{today}", headers=headers)
    assert get2.status_code == 200
    again = get2.json()
    assert again["main"][1] == ""


def test_overwrite_plan_removes_previous_extra_lines(client, auth_token, user_id):
    today = str(date.today())
    headers = {"Authorization": f"Bearer {auth_token}"}
    initial = _plan_payload(user_id, today, main=["Line1", "Line2", "Line3"])
    client.put(f"/daily-plans/{user_id}/{today}", json=initial, headers=headers)
    # Overwrite with fewer lines
    updated = _plan_payload(user_id, today, main=["New1"], notes="Shrink")
    put2 = client.put(f"/daily-plans/{user_id}/{today}", json=updated, headers=headers)
    assert put2.status_code == 200
    body = put2.json()
    assert body["main"] == ["New1"]
    assert body["notes"] == "Shrink"

    get2 = client.get(f"/daily-plans/{user_id}/{today}", headers=headers)
    assert get2.status_code == 200
    final = get2.json()
    assert final["main"] == ["New1"]


def test_large_plan_save(client, auth_token, user_id):
    today = str(date.today())
    headers = {"Authorization": f"Bearer {auth_token}"}
    big_list = [f"Item {i}" for i in range(1, 31)]  # 30 lines
    payload = _plan_payload(user_id, today, main=big_list, notes="Large plan")
    r = client.put(f"/daily-plans/{user_id}/{today}", json=payload, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data["main"]) == 30
    assert data["main"][0] == "Item 1"
    assert data["main"][-1] == "Item 30"

    # Fetch again
    r2 = client.get(f"/daily-plans/{user_id}/{today}", headers=headers)
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["main"]) == 30
