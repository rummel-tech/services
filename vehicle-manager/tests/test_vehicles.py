"""
Tests for vehicle-manager API endpoints.
"""

import pytest


class TestHealthEndpoints:
    """Tests for health and readiness endpoints."""

    def test_health_check(self, client):
        """Test the health check endpoint returns ok status."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "vehicle-manager"

    def test_readiness_check(self, client):
        """Test the readiness check endpoint returns ready status."""
        response = client.get("/ready")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ready"
        assert data["service"] == "vehicle-manager"

    def test_root_endpoint(self, client):
        """Test the root endpoint returns service info."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["service"] == "vehicle-manager"
        assert data["status"] == "operational"
        assert "version" in data
        assert "endpoints" in data


class TestVehicles:
    """Tests for vehicles endpoints."""

    def test_get_vehicles_success(self, client):
        """Test getting all vehicles for a user."""
        response = client.get("/vehicles/user-123")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == "user-123"
        assert "vehicles" in data
        assert len(data["vehicles"]) == 2  # Expected mock data count

    def test_vehicles_structure(self, client):
        """Test that vehicles have proper structure."""
        response = client.get("/vehicles/user-123")
        data = response.json()

        for vehicle in data["vehicles"]:
            assert "id" in vehicle
            assert "make" in vehicle
            assert "model" in vehicle
            assert "year" in vehicle
            assert "current_mileage" in vehicle

    def test_get_single_vehicle_success(self, client):
        """Test getting a specific vehicle by ID."""
        response = client.get("/vehicles/user-123/v1")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == "v1"
        assert data["make"] == "Toyota"
        assert data["model"] == "Camry"

    def test_get_vehicle_not_found(self, client):
        """Test that requesting nonexistent vehicle returns 404."""
        response = client.get("/vehicles/user-123/nonexistent")
        assert response.status_code == 404

        data = response.json()
        assert "error" in data
        assert data["error"]["type"] == "http_exception"
        assert "not found" in data["error"]["message"].lower()

    def test_vehicles_different_users(self, client):
        """Test that different user IDs are accepted."""
        response1 = client.get("/vehicles/user-abc")
        response2 = client.get("/vehicles/user-xyz")

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["user_id"] == "user-abc"
        assert response2.json()["user_id"] == "user-xyz"


class TestMaintenance:
    """Tests for maintenance endpoints."""

    def test_get_maintenance_records(self, client):
        """Test getting maintenance records for a vehicle."""
        response = client.get("/maintenance/v1")
        assert response.status_code == 200

        data = response.json()
        assert data["vehicle_id"] == "v1"
        assert "records" in data
        assert len(data["records"]) == 4  # Expected mock data count

    def test_maintenance_records_structure(self, client):
        """Test that maintenance records have proper structure."""
        response = client.get("/maintenance/v1")
        data = response.json()

        for record in data["records"]:
            assert "id" in record
            assert "vehicle_id" in record
            assert "date" in record
            assert "type" in record
            assert "mileage" in record

    def test_get_maintenance_by_type(self, client):
        """Test getting maintenance records filtered by type."""
        response = client.get("/maintenance/v1/type/oil_change")
        assert response.status_code == 200

        data = response.json()
        assert data["vehicle_id"] == "v1"
        assert data["type"] == "oil_change"

        # All records should be oil_change type
        for record in data["records"]:
            assert record["type"] == "oil_change"

    def test_get_maintenance_by_nonexistent_type(self, client):
        """Test getting maintenance with a type that has no records."""
        response = client.get("/maintenance/v1/type/nonexistent")
        assert response.status_code == 200

        data = response.json()
        assert data["records"] == []


class TestFuel:
    """Tests for fuel tracking endpoints."""

    def test_get_fuel_records(self, client):
        """Test getting fuel records for a vehicle."""
        response = client.get("/fuel/v1")
        assert response.status_code == 200

        data = response.json()
        assert data["vehicle_id"] == "v1"
        assert "records" in data
        assert len(data["records"]) == 3  # Expected mock data count

    def test_fuel_records_structure(self, client):
        """Test that fuel records have proper structure."""
        response = client.get("/fuel/v1")
        data = response.json()

        for record in data["records"]:
            assert "id" in record
            assert "vehicle_id" in record
            assert "date" in record
            assert "mileage" in record
            assert "gallons" in record
            assert "cost" in record
            assert "mpg" in record

    def test_get_fuel_records_with_limit(self, client):
        """Test getting fuel records with limit parameter."""
        response = client.get("/fuel/v1?limit=2")
        assert response.status_code == 200

        data = response.json()
        assert len(data["records"]) == 2

    def test_fuel_mpg_values_valid(self, client):
        """Test that MPG values are within reasonable range."""
        response = client.get("/fuel/v1")
        data = response.json()

        for record in data["records"]:
            assert 10 <= record["mpg"] <= 60  # Reasonable MPG range


class TestSchedule:
    """Tests for maintenance schedule endpoint."""

    def test_get_maintenance_schedule(self, client):
        """Test getting maintenance schedule for a vehicle."""
        response = client.get("/schedule/v1")
        assert response.status_code == 200

        data = response.json()
        assert data["vehicle_id"] == "v1"
        assert "current_mileage" in data
        assert "schedules" in data

    def test_schedule_structure(self, client):
        """Test that schedule items have proper structure."""
        response = client.get("/schedule/v1")
        data = response.json()

        for schedule in data["schedules"]:
            assert "id" in schedule
            assert "service_type" in schedule
            assert "interval_miles" in schedule
            assert "last_service_mileage" in schedule
            assert "next_due_mileage" in schedule
            assert "status" in schedule

    def test_schedule_status_values(self, client):
        """Test that schedule status is one of expected values."""
        response = client.get("/schedule/v1")
        data = response.json()

        valid_statuses = {"upcoming", "due", "overdue"}
        for schedule in data["schedules"]:
            assert schedule["status"] in valid_statuses


class TestStats:
    """Tests for vehicle statistics endpoint."""

    def test_get_vehicle_stats(self, client):
        """Test getting statistics for a vehicle."""
        response = client.get("/stats/v1")
        assert response.status_code == 200

        data = response.json()
        assert data["vehicle_id"] == "v1"
        assert "fuel" in data
        assert "maintenance" in data

    def test_stats_fuel_structure(self, client):
        """Test that fuel stats have proper structure."""
        response = client.get("/stats/v1")
        data = response.json()

        fuel_stats = data["fuel"]
        assert "total_cost" in fuel_stats
        assert "total_gallons" in fuel_stats
        assert "average_mpg" in fuel_stats
        assert "fill_ups" in fuel_stats

    def test_stats_maintenance_structure(self, client):
        """Test that maintenance stats have proper structure."""
        response = client.get("/stats/v1")
        data = response.json()

        maint_stats = data["maintenance"]
        assert "total_cost" in maint_stats
        assert "services" in maint_stats
        assert "last_service_date" in maint_stats


class TestSummary:
    """Tests for user summary endpoint."""

    def test_get_user_summary(self, client):
        """Test getting summary for all user vehicles."""
        response = client.get("/summary/user-123")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == "user-123"
        assert "total_vehicles" in data
        assert "total_fuel_cost" in data
        assert "total_maintenance_cost" in data
        assert "total_cost" in data

    def test_summary_total_cost_calculation(self, client):
        """Test that total cost is sum of fuel and maintenance."""
        response = client.get("/summary/user-123")
        data = response.json()

        expected_total = data["total_fuel_cost"] + data["total_maintenance_cost"]
        assert abs(data["total_cost"] - expected_total) < 0.01  # Float comparison

    def test_summary_vehicle_count(self, client):
        """Test that vehicle count matches expected."""
        response = client.get("/summary/user-123")
        data = response.json()

        assert data["total_vehicles"] == 2  # Expected mock data count


class TestErrorHandling:
    """Tests for error handling."""

    def test_invalid_endpoint_404(self, client):
        """Test that invalid endpoints return proper 404 response."""
        response = client.get("/invalid/endpoint")
        assert response.status_code == 404

        data = response.json()
        assert "error" in data
        assert data["error"]["type"] == "http_exception"

    def test_error_response_structure(self, client):
        """Test that error responses have proper structure."""
        response = client.get("/invalid/endpoint")

        data = response.json()
        assert "timestamp" in data
        assert "path" in data
        assert "method" in data
        assert "status_code" in data
        assert "correlation_id" in data
        assert "error" in data

    def test_vehicle_not_found_error_structure(self, client):
        """Test that vehicle not found returns proper error structure."""
        response = client.get("/vehicles/user-123/invalid-vehicle-id")
        assert response.status_code == 404

        data = response.json()
        assert data["status_code"] == 404
        assert data["error"]["type"] == "http_exception"

    def test_correlation_id_in_response_header(self, client):
        """Test that X-Request-ID header is present in responses."""
        response = client.get("/health")
        assert "x-request-id" in response.headers

    def test_response_time_header(self, client):
        """Test that X-Response-Time-Ms header is present."""
        response = client.get("/health")
        assert "x-response-time-ms" in response.headers


class TestSecurityHeaders:
    """Tests for security headers."""

    def test_security_headers_present(self, client):
        """Test that security headers are present in responses."""
        response = client.get("/health")

        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("x-frame-options") == "DENY"
        assert response.headers.get("x-xss-protection") == "1; mode=block"
        assert "strict-origin" in response.headers.get("referrer-policy", "")
