"""Tests for Artemis contract endpoints in meal-planner."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jose import jwt

SERVICE_ROOT = Path(__file__).resolve().parents[1]
SERVICES_ROOT = SERVICE_ROOT.parent
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICES_ROOT))

# ── test token ────────────────────────────────────────────────────────────────

TEST_USER = "artemis-meal-test-user"
_TOKEN = jwt.encode(
    {"sub": TEST_USER, "email": "meal@test.local", "iss": "artemis-auth"},
    "test-secret",
    algorithm="HS256",
)
AUTH = {"Authorization": f"Bearer {_TOKEN}"}


def _setup_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS meals (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            meal_type TEXT NOT NULL,
            date TEXT NOT NULL,
            calories INTEGER,
            protein_g INTEGER,
            carbs_g INTEGER,
            fat_g INTEGER,
            notes TEXT
        );
    """)
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def client():
    tmp = tempfile.mktemp(suffix=".db")
    _setup_db(tmp)
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp}"

    # Reset module-level USE_SQLITE cache
    import importlib
    if "routers.artemis" in sys.modules:
        del sys.modules["routers.artemis"]
    if "main" in sys.modules:
        del sys.modules["main"]

    from main import app  # noqa: E402
    with TestClient(app) as c:
        yield c

    os.unlink(tmp)


# ── manifest ──────────────────────────────────────────────────────────────────

def test_manifest(client):
    r = client.get("/artemis/manifest")
    assert r.status_code == 200
    data = r.json()
    assert data["module"]["id"] == "meal-planner"
    assert data["module"]["contract_version"] == "1.0"
    assert len(data["capabilities"]["dashboard_widgets"]) >= 1
    assert len(data["capabilities"]["agent_tools"]) >= 2


# ── auth enforcement ──────────────────────────────────────────────────────────

def test_widget_requires_auth(client):
    r = client.get("/artemis/widgets/todays_nutrition")
    assert r.status_code == 401


def test_agent_requires_auth(client):
    r = client.get("/artemis/agent/get_todays_meals")
    assert r.status_code == 401


# ── widgets ───────────────────────────────────────────────────────────────────

def test_widget_todays_nutrition_empty(client):
    r = client.get("/artemis/widgets/todays_nutrition", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["widget_id"] == "todays_nutrition"
    assert data["data"]["total_calories"] == 0
    assert data["data"]["meal_count"] == 0


def test_widget_weekly_calories(client):
    r = client.get("/artemis/widgets/weekly_calories", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["widget_id"] == "weekly_calories"
    assert len(data["data"]["days"]) == 7


def test_widget_unknown(client):
    r = client.get("/artemis/widgets/unknown_widget", headers=AUTH)
    assert r.status_code == 404


# ── agent tools ───────────────────────────────────────────────────────────────

def test_agent_get_todays_meals_empty(client):
    r = client.get("/artemis/agent/get_todays_meals", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["result"]["total_calories"] == 0


def test_agent_log_meal(client):
    r = client.post("/artemis/agent/log_meal", headers=AUTH, json={
        "name": "Oatmeal",
        "meal_type": "breakfast",
        "calories": 350,
        "protein_g": 12,
        "carbs_g": 60,
        "fat_g": 6,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["result"]["name"] == "Oatmeal"
    assert "meal_id" in data["result"]


def test_agent_log_meal_missing_name(client):
    r = client.post("/artemis/agent/log_meal", headers=AUTH, json={"meal_type": "lunch"})
    assert r.status_code == 400


def test_agent_log_meal_missing_type(client):
    r = client.post("/artemis/agent/log_meal", headers=AUTH, json={"name": "Chicken"})
    assert r.status_code == 400


def test_agent_get_todays_meals_after_log(client):
    r = client.get("/artemis/agent/get_todays_meals", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["result"]["total_calories"] == 350
    assert len(data["result"]["meals"]) == 1


def test_agent_get_weekly_nutrition(client):
    r = client.get("/artemis/agent/get_weekly_nutrition", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert "days" in data["result"]
    assert len(data["result"]["days"]) == 7
    assert "averages" in data["result"]


# ── cross-module data ─────────────────────────────────────────────────────────

def test_data_daily_calories(client):
    r = client.get("/artemis/data/daily_calories", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["data_id"] == "daily_calories"
    assert data["data"]["calories"] == 350


def test_data_unknown(client):
    r = client.get("/artemis/data/unknown", headers=AUTH)
    assert r.status_code == 404
