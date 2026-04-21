"""Tests for vehicle-manager CRUD API: vehicles, maintenance, fuel, stats."""
import pytest


VEHICLE_PAYLOAD = {
    "user_id": "user-123",
    "name": "2021 Toyota Camry",
    "asset_type": "vehicle",
    "category": "sedan",
    "manufacturer": "Toyota",
    "model_number": "Camry",
    "vin": "1HGBH41JXMN109186",
}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_ready(self, client):
        r = client.get("/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    def test_security_headers(self, client):
        r = client.get("/health")
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"

    def test_correlation_id_header(self, client):
        r = client.get("/health")
        assert "x-request-id" in r.headers


# ---------------------------------------------------------------------------
# Vehicles CRUD
# ---------------------------------------------------------------------------

class TestVehicles:
    def test_list_vehicles_empty(self, client):
        r = client.get("/vehicles/no-such-user")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_vehicle(self, client):
        r = client.post("/vehicles", json=VEHICLE_PAYLOAD)
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "2021 Toyota Camry"
        assert data["manufacturer"] == "Toyota"
        assert data["vin"] == "1HGBH41JXMN109186"
        assert "id" in data

    def test_create_vehicle_missing_required(self, client):
        r = client.post("/vehicles", json={"user_id": "user-123"})
        assert r.status_code == 422

    def test_list_vehicles_after_create(self, client):
        client.post("/vehicles", json={**VEHICLE_PAYLOAD, "user_id": "list-veh-user"})
        r = client.get("/vehicles/list-veh-user")
        assert r.status_code == 200
        vehicles = r.json()
        assert isinstance(vehicles, list)
        assert len(vehicles) >= 1

    def test_get_vehicle_by_id(self, client):
        created = client.post("/vehicles", json={**VEHICLE_PAYLOAD, "user_id": "get-veh-user"}).json()
        vehicle_id = created["id"]

        r = client.get(f"/vehicles/get-veh-user/{vehicle_id}")
        assert r.status_code == 200
        assert r.json()["id"] == vehicle_id
        assert r.json()["name"] == "2021 Toyota Camry"

    def test_get_vehicle_not_found(self, client):
        r = client.get("/vehicles/user-123/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404
        data = r.json()
        assert "error" in data

    def test_vehicles_for_different_users_are_isolated(self, client):
        client.post("/vehicles", json={**VEHICLE_PAYLOAD, "user_id": "iso-user-a"})
        client.post("/vehicles", json={**VEHICLE_PAYLOAD, "user_id": "iso-user-b"})

        r_a = client.get("/vehicles/iso-user-a")
        r_b = client.get("/vehicles/iso-user-b")
        assert all(v["user_id"] == "iso-user-a" for v in r_a.json())
        assert all(v["user_id"] == "iso-user-b" for v in r_b.json())


# ---------------------------------------------------------------------------
# Maintenance CRUD
# ---------------------------------------------------------------------------

class TestMaintenance:
    def _create_vehicle(self, client, user_id="maint-user"):
        return client.post("/vehicles", json={**VEHICLE_PAYLOAD, "user_id": user_id}).json()

    def test_list_maintenance_empty(self, client):
        v = self._create_vehicle(client, "maint-empty-user")
        r = client.get(f"/maintenance/{v['id']}")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_maintenance_record(self, client):
        v = self._create_vehicle(client, "maint-create-user")
        r = client.post("/maintenance", json={
            "user_id": "maint-create-user",
            "asset_id": v["id"],
            "maintenance_type": "oil_change",
            "date": "2026-01-15T10:00:00Z",
            "cost": 49.99,
            "performed_by": "Quick Lube",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["maintenance_type"] == "oil_change"
        assert data["cost"] == 49.99
        assert data["asset_id"] == v["id"]

    def test_list_maintenance_after_create(self, client):
        v = self._create_vehicle(client, "maint-list-user")
        client.post("/maintenance", json={
            "user_id": "maint-list-user",
            "asset_id": v["id"],
            "maintenance_type": "tire_rotation",
            "date": "2026-02-01T09:00:00Z",
            "cost": 25.0,
        })
        r = client.get(f"/maintenance/{v['id']}")
        assert r.status_code == 200
        records = r.json()
        assert len(records) >= 1
        assert records[0]["maintenance_type"] == "tire_rotation"

    def test_maintenance_record_structure(self, client):
        v = self._create_vehicle(client, "maint-struct-user")
        client.post("/maintenance", json={
            "user_id": "maint-struct-user",
            "asset_id": v["id"],
            "maintenance_type": "brake_pad",
            "date": "2026-03-01T08:00:00Z",
        })
        r = client.get(f"/maintenance/{v['id']}")
        record = r.json()[0]
        for field in ("id", "asset_id", "maintenance_type", "date"):
            assert field in record


# ---------------------------------------------------------------------------
# Fuel records
# ---------------------------------------------------------------------------

class TestFuel:
    def _create_vehicle(self, client, user_id="fuel-user"):
        return client.post("/vehicles", json={**VEHICLE_PAYLOAD, "user_id": user_id}).json()

    def test_list_fuel_empty(self, client):
        v = self._create_vehicle(client, "fuel-empty-user")
        r = client.get(f"/fuel/{v['id']}")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_fuel_record(self, client):
        v = self._create_vehicle(client, "fuel-create-user")
        r = client.post("/fuel", json={
            "user_id": "fuel-create-user",
            "asset_id": v["id"],
            "date": "2026-04-01T12:00:00Z",
            "mileage": 45000,
            "gallons": 12.5,
            "cost": 47.50,
            "price_per_gallon": 3.80,
        })
        assert r.status_code == 201
        data = r.json()
        assert data["mileage"] == 45000
        assert data["gallons"] == 12.5
        assert data["cost"] == 47.50

    def test_list_fuel_after_create(self, client):
        v = self._create_vehicle(client, "fuel-list-user")
        client.post("/fuel", json={
            "user_id": "fuel-list-user",
            "asset_id": v["id"],
            "date": "2026-04-05T12:00:00Z",
            "mileage": 46000,
            "gallons": 11.0,
            "cost": 41.80,
        })
        r = client.get(f"/fuel/{v['id']}")
        assert r.status_code == 200
        records = r.json()
        assert len(records) >= 1

    def test_fuel_limit_param(self, client):
        v = self._create_vehicle(client, "fuel-limit-user")
        for i in range(3):
            client.post("/fuel", json={
                "user_id": "fuel-limit-user",
                "asset_id": v["id"],
                "date": f"2026-04-{i+1:02d}T12:00:00Z",
                "mileage": 40000 + i * 500,
                "gallons": 10.0,
                "cost": 38.0,
            })
        r = client.get(f"/fuel/{v['id']}?limit=2")
        assert r.status_code == 200
        assert len(r.json()) <= 2

    def test_fuel_record_structure(self, client):
        v = self._create_vehicle(client, "fuel-struct-user")
        client.post("/fuel", json={
            "user_id": "fuel-struct-user",
            "asset_id": v["id"],
            "date": "2026-04-10T12:00:00Z",
            "mileage": 50000,
            "gallons": 13.0,
            "cost": 49.40,
        })
        record = client.get(f"/fuel/{v['id']}").json()[0]
        for field in ("id", "asset_id", "date", "mileage", "gallons", "cost"):
            assert field in record


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_vehicle_stats_empty(self, client):
        v = client.post("/vehicles", json={**VEHICLE_PAYLOAD, "user_id": "stats-user"}).json()
        r = client.get(f"/stats/{v['id']}")
        assert r.status_code == 200
        data = r.json()
        assert "fuel" in data
        assert "maintenance" in data

    def test_vehicle_stats_fuel_structure(self, client):
        v = client.post("/vehicles", json={**VEHICLE_PAYLOAD, "user_id": "stats-fuel-user"}).json()
        r = client.get(f"/stats/{v['id']}")
        fuel = r.json()["fuel"]
        for field in ("total_cost", "total_gallons", "fill_ups"):
            assert field in fuel

    def test_vehicle_stats_maintenance_structure(self, client):
        v = client.post("/vehicles", json={**VEHICLE_PAYLOAD, "user_id": "stats-maint-user"}).json()
        r = client.get(f"/stats/{v['id']}")
        maint = r.json()["maintenance"]
        for field in ("total_cost", "services"):
            assert field in maint


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_vehicle_not_found_structure(self, client):
        r = client.get("/vehicles/user-123/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404
        data = r.json()
        assert "error" in data
        assert "timestamp" in data
        assert "correlation_id" in data

    def test_invalid_route(self, client):
        r = client.get("/nonexistent/route")
        assert r.status_code == 404
