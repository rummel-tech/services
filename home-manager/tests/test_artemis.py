"""Tests for Artemis contract endpoints in home-manager."""
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

TEST_USER = "artemis-home-test-user"
_TOKEN = jwt.encode(
    {"sub": TEST_USER, "email": "home@test.local", "iss": "artemis-auth"},
    "test-secret",
    algorithm="HS256",
)
AUTH = {"Authorization": f"Bearer {_TOKEN}"}


def _setup_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'open',
            priority TEXT DEFAULT 'medium',
            category TEXT,
            due_date TEXT,
            estimated_minutes INTEGER,
            tags TEXT,
            context TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            asset_type TEXT NOT NULL,
            category TEXT,
            manufacturer TEXT,
            model_number TEXT,
            serial_number TEXT,
            purchase_date TEXT,
            purchase_price REAL,
            condition TEXT DEFAULT 'good',
            location TEXT,
            notes TEXT,
            context TEXT DEFAULT '{}'
        );
    """)
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def client():
    tmp = tempfile.mktemp(suffix=".db")
    _setup_db(tmp)
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp}"

    for mod in list(sys.modules.keys()):
        if mod in ("routers.artemis", "main"):
            del sys.modules[mod]

    from main import app  # noqa: E402
    with TestClient(app) as c:
        yield c

    os.unlink(tmp)


# ── manifest ──────────────────────────────────────────────────────────────────

def test_manifest(client):
    r = client.get("/artemis/manifest")
    assert r.status_code == 200
    data = r.json()
    assert data["module"]["id"] == "home-manager"
    assert data["module"]["contract_version"] == "1.0"
    assert len(data["capabilities"]["agent_tools"]) >= 3


# ── auth enforcement ──────────────────────────────────────────────────────────

def test_widget_requires_auth(client):
    r = client.get("/artemis/widgets/open_tasks")
    assert r.status_code == 401


# ── widgets ───────────────────────────────────────────────────────────────────

def test_widget_open_tasks_empty(client):
    r = client.get("/artemis/widgets/open_tasks", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["widget_id"] == "open_tasks"
    assert data["data"]["count"] == 0


def test_widget_upcoming_tasks(client):
    r = client.get("/artemis/widgets/upcoming_tasks", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["widget_id"] == "upcoming_tasks"


def test_widget_unknown(client):
    r = client.get("/artemis/widgets/nope", headers=AUTH)
    assert r.status_code == 404


# ── agent tools ───────────────────────────────────────────────────────────────

def test_agent_list_tasks_empty(client):
    r = client.get("/artemis/agent/list_tasks", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["result"]["count"] == 0


def test_agent_create_task(client):
    r = client.post("/artemis/agent/create_task", headers=AUTH, json={
        "title": "Fix leaky faucet",
        "priority": "high",
        "category": "plumbing",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["result"]["title"] == "Fix leaky faucet"
    assert "task_id" in data["result"]


def test_agent_create_task_missing_title(client):
    r = client.post("/artemis/agent/create_task", headers=AUTH, json={"priority": "low"})
    assert r.status_code == 400


def test_agent_list_tasks_after_create(client):
    r = client.get("/artemis/agent/list_tasks", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["result"]["count"] == 1
    assert data["result"]["tasks"][0]["title"] == "Fix leaky faucet"


def test_agent_complete_task(client):
    # Get task id first
    r = client.get("/artemis/agent/list_tasks", headers=AUTH)
    task_id = r.json()["result"]["tasks"][0]["id"]

    r = client.post("/artemis/agent/complete_task", headers=AUTH, json={"task_id": task_id})
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["result"]["status"] == "done"


def test_agent_complete_task_missing_id(client):
    r = client.post("/artemis/agent/complete_task", headers=AUTH, json={})
    assert r.status_code == 400


def test_agent_complete_task_not_found(client):
    r = client.post("/artemis/agent/complete_task", headers=AUTH, json={"task_id": "nonexistent"})
    assert r.status_code == 404


def test_agent_list_assets_empty(client):
    r = client.get("/artemis/agent/list_assets", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["result"]["count"] == 0


# ── cross-module data ─────────────────────────────────────────────────────────

def test_data_open_task_count(client):
    r = client.get("/artemis/data/open_task_count", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["data_id"] == "open_task_count"
    # completed task should not count
    assert data["data"]["count"] == 0


def test_data_unknown(client):
    r = client.get("/artemis/data/unknown", headers=AUTH)
    assert r.status_code == 404
