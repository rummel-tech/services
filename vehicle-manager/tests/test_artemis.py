"""Tests for Artemis contract endpoints in vehicle-manager."""
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

TEST_USER = "artemis-vehicle-test-user"
_TOKEN = jwt.encode(
    {"sub": TEST_USER, "email": "vehicle@test.local", "iss": "artemis-auth"},
    "test-secret",
    algorithm="HS256",
)
AUTH = {"Authorization": f"Bearer {_TOKEN}"}

VEHICLE_ID = None  # populated by test_agent_create_vehicle_via_existing_endpoint


def _setup_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            asset_type TEXT NOT NULL DEFAULT 'vehicle',
            category TEXT,
            manufacturer TEXT,
            model_number TEXT,
            serial_number TEXT,
            vin TEXT,
            purchase_date TEXT,
            purchase_price REAL,
            condition TEXT DEFAULT 'good',
            location TEXT,
            notes TEXT,
            context TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS maintenance_records (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            maintenance_type TEXT NOT NULL,
            date TEXT NOT NULL,
            cost REAL,
            description TEXT,
            performed_by TEXT,
            next_due_date TEXT,
            next_due_mileage INTEGER,
            notes TEXT,
            context TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS fuel_records (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            date TEXT NOT NULL,
            mileage INTEGER NOT NULL,
            gallons REAL NOT NULL,
            cost REAL NOT NULL,
            price_per_gallon REAL,
            fuel_type TEXT DEFAULT 'regular',
            mpg REAL,
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

    for mod in list(sys.modules.keys()):
        if mod in ("routers.artemis", "main"):
            del sys.modules[mod]

    from main import app  # noqa: E402
    with TestClient(app) as c:
        yield c

    os.unlink(tmp)


@pytest.fixture(scope="module")
def vehicle_id():
    """Seed a vehicle directly in SQLite, return its id."""
    import uuid
    vid = str(uuid.uuid4())
    db_path = os.environ["DATABASE_URL"].replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO assets (id, user_id, name, asset_type, category, manufacturer, model_number, condition) VALUES (?,?,?,?,?,?,?,?)",
        (vid, TEST_USER, "Test Truck", "vehicle", "truck", "Ford", "F-150", "good"),
    )
    conn.commit()
    conn.close()
    return vid


# ── manifest ──────────────────────────────────────────────────────────────────

def test_manifest(client):
    r = client.get("/artemis/manifest")
    assert r.status_code == 200
    data = r.json()
    assert data["module"]["id"] == "vehicle-manager"
    assert data["module"]["contract_version"] == "1.0"
    assert len(data["capabilities"]["agent_tools"]) >= 3


# ── auth enforcement ──────────────────────────────────────────────────────────

def test_widget_requires_auth(client):
    r = client.get("/artemis/widgets/fleet_overview")
    assert r.status_code == 401


# ── widgets ───────────────────────────────────────────────────────────────────

def test_widget_fleet_overview_empty(client):
    r = client.get("/artemis/widgets/fleet_overview", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["widget_id"] == "fleet_overview"
    assert data["data"]["vehicle_count"] == 0


def test_widget_fleet_overview_with_vehicle(client, vehicle_id):
    r = client.get("/artemis/widgets/fleet_overview", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["data"]["vehicle_count"] == 1


def test_widget_upcoming_maintenance(client, vehicle_id):
    r = client.get("/artemis/widgets/upcoming_maintenance", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["widget_id"] == "upcoming_maintenance"


def test_widget_unknown(client):
    r = client.get("/artemis/widgets/nope", headers=AUTH)
    assert r.status_code == 404


# ── agent tools ───────────────────────────────────────────────────────────────

def test_agent_list_vehicles_empty_before_seed(client):
    # vehicle_id fixture seeds data; this tests without it
    r = client.get("/artemis/agent/list_vehicles", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True


def test_agent_list_vehicles(client, vehicle_id):
    r = client.get("/artemis/agent/list_vehicles", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["result"]["count"] == 1
    assert data["result"]["vehicles"][0]["name"] == "Test Truck"


def test_agent_log_fuel(client, vehicle_id):
    r = client.post("/artemis/agent/log_fuel", headers=AUTH, json={
        "vehicle_id": vehicle_id,
        "mileage": 45000,
        "gallons": 15.2,
        "cost": 54.72,
        "fuel_type": "regular",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["result"]["gallons"] == 15.2
    assert "price_per_gallon" in data["result"]


def test_agent_log_fuel_missing_required(client, vehicle_id):
    r = client.post("/artemis/agent/log_fuel", headers=AUTH, json={"vehicle_id": vehicle_id})
    assert r.status_code == 400


def test_agent_log_maintenance(client, vehicle_id):
    r = client.post("/artemis/agent/log_maintenance", headers=AUTH, json={
        "vehicle_id": vehicle_id,
        "maintenance_type": "oil_change",
        "cost": 89.99,
        "description": "5W-30 synthetic",
        "next_due_date": "2026-09-28",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["result"]["maintenance_type"] == "oil_change"


def test_agent_get_vehicle_stats(client, vehicle_id):
    r = client.post("/artemis/agent/get_vehicle_stats", headers=AUTH, json={"vehicle_id": vehicle_id})
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["result"]["fuel"]["fill_ups"] == 1
    assert data["result"]["fuel"]["total_cost"] == 54.72
    assert data["result"]["maintenance"]["services"] == 1


# ── cross-module data ─────────────────────────────────────────────────────────

def test_data_fuel_costs(client, vehicle_id):
    r = client.get("/artemis/data/fuel_costs", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["data_id"] == "fuel_costs"
    assert data["data"]["total_cost"] == 54.72


def test_data_maintenance_costs(client, vehicle_id):
    r = client.get("/artemis/data/maintenance_costs", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["data_id"] == "maintenance_costs"
    assert data["data"]["total_cost"] == 89.99
    assert data["data"]["service_count"] == 1


def test_data_unknown(client):
    r = client.get("/artemis/data/unknown", headers=AUTH)
    assert r.status_code == 404
