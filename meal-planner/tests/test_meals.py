"""
Tests for meal-planner API endpoints.
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
        assert data["service"] == "meal-planner"

    def test_readiness_check(self, client):
        """Test the readiness check endpoint returns ready status."""
        response = client.get("/ready")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ready"
        assert data["service"] == "meal-planner"

    def test_root_endpoint(self, client):
        """Test the root endpoint returns service info."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["service"] == "meal-planner"
        assert data["status"] == "operational"
        assert "version" in data
        assert "endpoints" in data


class TestWeeklyMealPlan:
    """Tests for weekly meal plan endpoint."""

    def test_get_weekly_plan_success(self, client):
        """Test getting a weekly meal plan for a user."""
        response = client.get("/meals/weekly-plan/user-123")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == "user-123"
        assert data["focus"] == "balanced"
        assert "days" in data
        assert len(data["days"]) == 7

    def test_weekly_plan_has_all_days(self, client):
        """Test that weekly plan includes all days of the week."""
        response = client.get("/meals/weekly-plan/user-123")
        data = response.json()

        days = [d["day"] for d in data["days"]]
        expected_days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        assert days == expected_days

    def test_weekly_plan_meals_structure(self, client):
        """Test that each day has properly structured meals."""
        response = client.get("/meals/weekly-plan/user-123")
        data = response.json()

        for day in data["days"]:
            assert "day" in day
            assert "meals" in day
            assert len(day["meals"]) >= 1

            for meal in day["meals"]:
                assert "name" in meal
                assert "calories" in meal

    def test_weekly_plan_with_week_start(self, client):
        """Test getting weekly plan with optional week_start parameter."""
        response = client.get("/meals/weekly-plan/user-123?week_start=2025-12-01")
        assert response.status_code == 200

        data = response.json()
        assert data["week_start"] == "2025-12-01"

    def test_weekly_plan_different_users(self, client):
        """Test that different user IDs are accepted."""
        response1 = client.get("/meals/weekly-plan/user-abc")
        response2 = client.get("/meals/weekly-plan/user-xyz")

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["user_id"] == "user-abc"
        assert response2.json()["user_id"] == "user-xyz"


class TestTodayMeals:
    """Tests for today's meals endpoint."""

    def test_get_today_meals_default(self, client):
        """Test getting today's meals without specifying date."""
        response = client.get("/meals/today/user-123")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == "user-123"
        assert "day" in data
        assert "meals" in data
        assert "total_calories" in data

    def test_get_today_meals_with_date(self, client):
        """Test getting meals for a specific date (Monday)."""
        # 2025-12-01 is a Monday
        response = client.get("/meals/today/user-123?date=2025-12-01")
        assert response.status_code == 200

        data = response.json()
        assert data["day"] == "Monday"
        assert len(data["meals"]) >= 1
        assert data["total_calories"] > 0

    def test_today_meals_calorie_calculation(self, client):
        """Test that total calories are correctly summed."""
        response = client.get("/meals/today/user-123?date=2025-12-01")
        data = response.json()

        calculated_total = sum(m.get("calories", 0) for m in data["meals"])
        assert data["total_calories"] == calculated_total

    def test_today_meals_different_days(self, client):
        """Test getting meals for different days of the week."""
        # Monday
        r1 = client.get("/meals/today/user-123?date=2025-12-01")
        # Wednesday
        r2 = client.get("/meals/today/user-123?date=2025-12-03")

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["day"] == "Monday"
        assert r2.json()["day"] == "Wednesday"


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
