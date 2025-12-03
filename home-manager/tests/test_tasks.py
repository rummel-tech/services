"""
Tests for home-manager API endpoints.
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
        assert data["service"] == "home-manager"

    def test_readiness_check(self, client):
        """Test the readiness check endpoint returns ready status."""
        response = client.get("/ready")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ready"
        assert data["service"] == "home-manager"

    def test_root_endpoint(self, client):
        """Test the root endpoint returns service info."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["service"] == "home-manager"
        assert data["status"] == "operational"
        assert "version" in data
        assert "endpoints" in data


class TestWeeklyTasks:
    """Tests for weekly tasks endpoint."""

    def test_get_weekly_tasks_success(self, client):
        """Test getting weekly tasks for a user."""
        response = client.get("/tasks/weekly/user-123")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == "user-123"
        assert "tasks" in data
        assert len(data["tasks"]) == 14  # Expected mock data count

    def test_weekly_tasks_structure(self, client):
        """Test that tasks have proper structure."""
        response = client.get("/tasks/weekly/user-123")
        data = response.json()

        for task in data["tasks"]:
            assert "id" in task
            assert "title" in task
            assert "day" in task
            assert "category" in task
            assert "priority" in task
            assert "completed" in task

    def test_weekly_tasks_with_week_start(self, client):
        """Test getting weekly tasks with optional week_start parameter."""
        response = client.get("/tasks/weekly/user-123?week_start=2025-12-01")
        assert response.status_code == 200

        data = response.json()
        assert data["week_start"] == "2025-12-01"

    def test_weekly_tasks_different_users(self, client):
        """Test that different user IDs are accepted."""
        response1 = client.get("/tasks/weekly/user-abc")
        response2 = client.get("/tasks/weekly/user-xyz")

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["user_id"] == "user-abc"
        assert response2.json()["user_id"] == "user-xyz"


class TestTodayTasks:
    """Tests for today's tasks endpoint."""

    def test_get_today_tasks_default(self, client):
        """Test getting today's tasks without specifying date."""
        response = client.get("/tasks/today/user-123")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == "user-123"
        assert "day" in data
        assert "tasks" in data
        assert "total_estimated_minutes" in data

    def test_get_today_tasks_monday(self, client):
        """Test getting tasks for Monday."""
        # 2025-12-01 is a Monday
        response = client.get("/tasks/today/user-123?date=2025-12-01")
        assert response.status_code == 200

        data = response.json()
        assert data["day"] == "Monday"
        # Check all returned tasks are for Monday
        for task in data["tasks"]:
            assert task["day"] == "Monday"

    def test_today_tasks_time_estimate_calculation(self, client):
        """Test that total estimated minutes are correctly summed."""
        response = client.get("/tasks/today/user-123?date=2025-12-01")
        data = response.json()

        calculated_total = sum(t.get("estimated_minutes", 0) for t in data["tasks"])
        assert data["total_estimated_minutes"] == calculated_total

    def test_today_tasks_different_days(self, client):
        """Test getting tasks for different days of the week."""
        # Monday
        r1 = client.get("/tasks/today/user-123?date=2025-12-01")
        # Wednesday
        r2 = client.get("/tasks/today/user-123?date=2025-12-03")

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["day"] == "Monday"
        assert r2.json()["day"] == "Wednesday"


class TestTasksByCategory:
    """Tests for tasks by category endpoint."""

    def test_get_tasks_by_category_cleaning(self, client):
        """Test getting tasks filtered by cleaning category."""
        response = client.get("/tasks/category/user-123/cleaning")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == "user-123"
        assert data["category"] == "cleaning"
        assert "tasks" in data

        # All tasks should be in cleaning category
        for task in data["tasks"]:
            assert task["category"] == "cleaning"

    def test_get_tasks_by_category_chores(self, client):
        """Test getting tasks filtered by chores category."""
        response = client.get("/tasks/category/user-123/chores")
        assert response.status_code == 200

        data = response.json()
        assert len(data["tasks"]) >= 1

    def test_get_tasks_by_nonexistent_category(self, client):
        """Test getting tasks with a category that has no tasks."""
        response = client.get("/tasks/category/user-123/nonexistent")
        assert response.status_code == 200

        data = response.json()
        assert data["tasks"] == []


class TestGoals:
    """Tests for goals endpoint."""

    def test_get_goals_success(self, client):
        """Test getting goals for a user."""
        response = client.get("/goals/user-123")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == "user-123"
        assert "goals" in data
        assert len(data["goals"]) == 3  # Expected mock data count

    def test_goals_structure(self, client):
        """Test that goals have proper structure."""
        response = client.get("/goals/user-123")
        data = response.json()

        for goal in data["goals"]:
            assert "id" in goal
            assert "title" in goal
            assert "category" in goal
            assert "progress" in goal
            assert "is_active" in goal

    def test_goals_progress_range(self, client):
        """Test that goal progress is within valid range."""
        response = client.get("/goals/user-123")
        data = response.json()

        for goal in data["goals"]:
            assert 0 <= goal["progress"] <= 100


class TestStats:
    """Tests for statistics endpoint."""

    def test_get_stats_success(self, client):
        """Test getting statistics for a user."""
        response = client.get("/stats/user-123")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == "user-123"
        assert "tasks" in data
        assert "goals" in data

    def test_stats_tasks_structure(self, client):
        """Test that task stats have proper structure."""
        response = client.get("/stats/user-123")
        data = response.json()

        task_stats = data["tasks"]
        assert "total" in task_stats
        assert "completed" in task_stats
        assert "completion_rate" in task_stats
        assert "total_estimated_minutes" in task_stats

    def test_stats_goals_structure(self, client):
        """Test that goal stats have proper structure."""
        response = client.get("/stats/user-123")
        data = response.json()

        goal_stats = data["goals"]
        assert "total" in goal_stats
        assert "active" in goal_stats
        assert "average_progress" in goal_stats

    def test_stats_completion_rate_valid(self, client):
        """Test that completion rate is within valid range."""
        response = client.get("/stats/user-123")
        data = response.json()

        assert 0 <= data["tasks"]["completion_rate"] <= 100


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
