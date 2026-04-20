"""Basic tests for trip-planner API."""
import os
import sys
import pytest

# Use SQLite in-memory for tests
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DISABLE_AUTH", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient

# Initialize DB before importing app
from core.database import init_db
init_db()

from main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer test-token"}


def test_liveness():
    resp = client.get("/api/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_and_list_trip():
    resp = client.post(
        "/api/trips",
        json={
            "name": "Summer Road Trip",
            "destination": "Yellowstone National Park",
            "trip_type": "road_trip",
            "start_date": "2026-07-10",
            "end_date": "2026-07-17",
            "budget_cents": 300000,
        },
        headers=AUTH,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Summer Road Trip"
    assert data["destination"] == "Yellowstone National Park"
    assert data["total_days"] == 8
    assert data["budget_cents"] == 300000
    assert data["spent_cents"] == 0
    assert data["remaining_cents"] == 300000
    trip_id = data["id"]

    # List trips
    list_resp = client.get("/api/trips", headers=AUTH)
    assert list_resp.status_code == 200
    ids = [t["id"] for t in list_resp.json()]
    assert trip_id in ids


def test_packing_seed():
    # Create a camping trip
    resp = client.post(
        "/api/trips",
        json={
            "name": "Camping Weekend",
            "destination": "Glacier NP",
            "trip_type": "camping",
        },
        headers=AUTH,
    )
    assert resp.status_code == 201
    trip_id = resp.json()["id"]

    # Seed packing list
    seed_resp = client.post(f"/api/trips/{trip_id}/packing/seed", headers=AUTH)
    assert seed_resp.status_code == 201
    items = seed_resp.json()
    assert len(items) > 0
    names = [i["name"] for i in items]
    assert "Tent" in names

    # Toggle packed
    item_id = items[0]["id"]
    patch_resp = client.patch(
        f"/api/trips/{trip_id}/packing/{item_id}",
        json={"packed": True},
        headers=AUTH,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["packed"] is True


def test_add_itinerary_item():
    resp = client.post(
        "/api/trips",
        json={"name": "Paris Trip", "destination": "Paris, France", "trip_type": "international"},
        headers=AUTH,
    )
    trip_id = resp.json()["id"]

    item_resp = client.post(
        f"/api/trips/{trip_id}/itinerary",
        json={
            "day_date": "2026-09-01",
            "title": "Eiffel Tower",
            "location": "Champ de Mars, Paris",
            "category": "activity",
            "start_time": "10:00",
            "end_time": "12:00",
            "cost_cents": 2600,
        },
        headers=AUTH,
    )
    assert item_resp.status_code == 201
    assert item_resp.json()["title"] == "Eiffel Tower"


def test_add_expense_and_budget():
    resp = client.post(
        "/api/trips",
        json={
            "name": "NYC Weekend",
            "destination": "New York City",
            "trip_type": "weekend",
            "budget_cents": 100000,
        },
        headers=AUTH,
    )
    trip_id = resp.json()["id"]

    client.post(
        f"/api/trips/{trip_id}/expenses",
        json={
            "category": "accommodation",
            "description": "Hotel Midtown",
            "amount_cents": 35000,
            "expense_date": "2026-08-15",
        },
        headers=AUTH,
    )
    client.post(
        f"/api/trips/{trip_id}/expenses",
        json={
            "category": "food",
            "description": "Dinner",
            "amount_cents": 8000,
            "expense_date": "2026-08-15",
        },
        headers=AUTH,
    )

    budget_resp = client.get(f"/api/trips/{trip_id}/budget", headers=AUTH)
    assert budget_resp.status_code == 200
    budget = budget_resp.json()
    assert budget["spent_cents"] == 43000
    assert budget["remaining_cents"] == 57000
    assert budget["by_category"]["accommodation"] == 35000
    assert budget["by_category"]["food"] == 8000
