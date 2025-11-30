"""
Integration tests for Workout Planner API

These tests verify complete user workflows across multiple endpoints,
testing the integration between different parts of the system.
"""
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, date, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create test client with isolated database"""
    test_file = Path(__file__).resolve()
    server_root = test_file.parents[1]
    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))

    tmp_db = os.path.join(tempfile.gettempdir(), "integration_test.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_db}"

    from database import init_sqlite  # type: ignore
    init_sqlite()
    from main import app  # type: ignore
    return TestClient(app)


class TestCompleteUserJourney:
    """Test a complete user journey from registration to workout planning"""

    def test_user_registration_to_workout_plan(self, client):
        """Test: Register → Login → Create daily plan → Update plan → Retrieve plan"""

        # Step 1: Register new user
        register_response = client.post(
            "/auth/register",
            json={"email": "journey1@example.com", "password": "SecurePass123!"}
        )
        assert register_response.status_code == 201
        tokens = register_response.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        access_token = tokens["access_token"]

        # Step 2: Get user info to extract user_id
        me_response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert me_response.status_code == 200
        user_id = str(me_response.json()["id"])

        # Step 3: Create a daily workout plan
        today = str(date.today())
        plan_data = {
            "user_id": user_id,
            "date": today,
            "plan_json": {
                "warmup": ["5 min jog", "Dynamic stretching"],
                "main": ["3x10 squats", "3x10 push-ups", "3x10 pull-ups"],
                "cooldown": ["5 min walk", "Static stretching"],
                "notes": "First workout of the week"
            },
            "status": "pending"
        }
        create_response = client.put(
            f"/daily-plans/{user_id}/{today}",
            json=plan_data,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert create_response.status_code == 200
        created_plan = create_response.json()
        assert created_plan["user_id"] == user_id
        assert len(created_plan["main"]) == 3

        # Step 4: Update the plan (mark as complete)
        updated_plan_data = plan_data.copy()
        updated_plan_data["status"] = "complete"
        updated_plan_data["plan_json"]["notes"] = "Workout completed successfully!"

        update_response = client.put(
            f"/daily-plans/{user_id}/{today}",
            json=updated_plan_data,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert update_response.status_code == 200
        updated_plan = update_response.json()
        assert updated_plan["status"] == "complete"
        assert "completed successfully" in updated_plan["notes"]

        # Step 5: Retrieve the plan to verify persistence
        get_response = client.get(
            f"/daily-plans/{user_id}/{today}",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert get_response.status_code == 200
        retrieved_plan = get_response.json()
        assert retrieved_plan["status"] == "complete"
        assert len(retrieved_plan["main"]) == 3

        # Step 6: Login again with same credentials
        login_response = client.post(
            "/auth/login",
            json={"email": "journey1@example.com", "password": "SecurePass123!"}
        )
        assert login_response.status_code == 200
        new_tokens = login_response.json()
        new_access_token = new_tokens["access_token"]

        # Step 7: Verify can still access plan with new token
        verify_response = client.get(
            f"/daily-plans/{user_id}/{today}",
            headers={"Authorization": f"Bearer {new_access_token}"}
        )
        assert verify_response.status_code == 200


class TestHealthDataWorkflow:
    """Test health data ingestion and readiness score calculation"""

    def test_health_data_to_readiness_score(self, client):
        """Test: Register → Ingest health samples → Calculate readiness → Verify score"""

        # Step 1: Register user
        register_response = client.post(
            "/auth/register",
            json={"email": "health1@example.com", "password": "HealthPass123!"}
        )
        assert register_response.status_code == 201
        access_token = register_response.json()["access_token"]

        # Step 2: Get user ID
        me_response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        user_id = str(me_response.json()["id"])

        # Step 3: Ingest baseline health data (from 7 days ago)
        baseline_time = (datetime.utcnow() - timedelta(days=7)).isoformat()
        baseline_samples = {
            "samples": [
                {
                    "user_id": user_id,
                    "sample_type": "hrv",
                    "value": 50.0,
                    "unit": "ms",
                    "start_time": baseline_time,
                    "end_time": baseline_time,
                    "source_uuid": f"baseline-hrv-{i}"
                }
                for i in range(5)
            ]
        }
        ingest_response = client.post(
            "/health/samples",
            json=baseline_samples,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert ingest_response.status_code == 200
        assert ingest_response.json()["inserted"] == 5

        # Step 4: Ingest recent health data (last 24 hours) - improved metrics
        recent_time = datetime.utcnow().isoformat()
        recent_samples = {
            "samples": [
                {
                    "user_id": user_id,
                    "sample_type": "hrv",
                    "value": 65.0,  # Better than baseline
                    "unit": "ms",
                    "start_time": recent_time,
                    "end_time": recent_time,
                    "source_uuid": f"recent-hrv-{i}"
                }
                for i in range(3)
            ]
        }
        recent_ingest = client.post(
            "/health/samples",
            json=recent_samples,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert recent_ingest.status_code == 200

        # Step 5: Calculate readiness score
        readiness_response = client.get(f"/readiness?user_id={user_id}")
        assert readiness_response.status_code == 200
        readiness_data = readiness_response.json()

        # Verify readiness calculation
        assert readiness_data["user_id"] == user_id
        assert readiness_data["hrv"] == 65.0
        assert 40.0 <= readiness_data["hrv_baseline"] <= 65.0  # Wider range for integration test
        assert readiness_data["scores"]["hrv"] > 0.5  # Better than baseline
        assert 0.0 <= readiness_data["readiness"] <= 1.0

        # Step 6: Query health samples to verify persistence
        samples_response = client.get(
            f"/health/samples?user_id={user_id}&sample_type=hrv",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert samples_response.status_code == 200
        samples = samples_response.json()
        assert len(samples) >= 8  # 5 baseline + 3 recent

        # Step 7: Get health summary
        summary_response = client.get(f"/health/summary?user_id={user_id}&days=14")
        assert summary_response.status_code == 200
        summary = summary_response.json()
        if "hrv" in summary:
            assert summary["hrv"]["count"] >= 8


class TestWeeklyPlanningWorkflow:
    """Test weekly planning across daily and weekly plans"""

    def test_weekly_planning_workflow(self, client):
        """Test: Register → Create weekly plan → Create daily plans → Retrieve all"""

        # Step 1: Register user
        register_response = client.post(
            "/auth/register",
            json={"email": "weekly1@example.com", "password": "WeeklyPass123!"}
        )
        access_token = register_response.json()["access_token"]

        me_response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        user_id = str(me_response.json()["id"])

        # Step 2: Create weekly workout plan
        weekly_plan = {
            "user_id": user_id,
            "focus": "strength",
            "days": [
                {"day": "Monday", "type": "Strength"},
                {"day": "Tuesday", "type": "Run"},
                {"day": "Wednesday", "type": "Strength"},
                {"day": "Thursday", "type": "Rest"},
                {"day": "Friday", "type": "Strength"},
                {"day": "Saturday", "type": "Swim"},
                {"day": "Sunday", "type": "Rest"}
            ]
        }
        weekly_response = client.put(
            f"/weekly-plans/{user_id}",
            json=weekly_plan,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert weekly_response.status_code == 200
        assert weekly_response.json()["focus"] == "strength"

        # Step 3: Create daily plans for strength days
        today = date.today()
        for i, day_plan in enumerate(weekly_plan["days"]):
            if day_plan["type"] == "Strength":
                plan_date = str(today + timedelta(days=i))
                daily_plan = {
                    "user_id": user_id,
                    "date": plan_date,
                    "plan_json": {
                        "warmup": ["Dynamic stretching"],
                        "main": ["Squats 5x5", "Bench Press 5x5", "Deadlifts 3x5"],
                        "cooldown": ["Static stretching"],
                        "notes": f"Strength workout for {day_plan['day']}"
                    },
                    "status": "pending"
                }
                daily_response = client.put(
                    f"/daily-plans/{user_id}/{plan_date}",
                    json=daily_plan,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                assert daily_response.status_code == 200

        # Step 4: Retrieve weekly plan
        get_weekly = client.get(
            f"/weekly-plans/{user_id}",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert get_weekly.status_code == 200
        retrieved_weekly = get_weekly.json()
        assert retrieved_weekly["focus"] == "strength"
        assert len(retrieved_weekly["days"]) == 7

        # Step 5: Get meal plan for the week
        meal_response = client.get(
            f"/meals/weekly-plan/{user_id}",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert meal_response.status_code == 200
        meal_plan = meal_response.json()
        assert meal_plan["user_id"] == user_id
        assert len(meal_plan["days"]) == 7


class TestAuthenticationFlow:
    """Test complete authentication and authorization flow"""

    def test_auth_token_refresh_flow(self, client):
        """Test: Register → Refresh token → Access resource → Logout"""

        # Step 1: Register
        register_response = client.post(
            "/auth/register",
            json={"email": "auth1@example.com", "password": "AuthPass123!"}
        )
        assert register_response.status_code == 201
        tokens = register_response.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]

        # Step 2: Access protected resource with access token
        me_response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert me_response.status_code == 200
        user_data = me_response.json()
        assert user_data["email"] == "auth1@example.com"

        # Step 3: Refresh the access token
        refresh_response = client.post(
            "/auth/refresh",
            headers={"Authorization": f"Bearer {refresh_token}"}
        )
        assert refresh_response.status_code == 200
        new_tokens = refresh_response.json()
        new_access_token = new_tokens["access_token"]
        assert new_access_token != access_token  # Should be different

        # Step 4: Access resource with new token
        me_response2 = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {new_access_token}"}
        )
        assert me_response2.status_code == 200
        assert me_response2.json()["email"] == "auth1@example.com"

        # Step 5: Logout
        logout_response = client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {new_access_token}"}
        )
        assert logout_response.status_code == 200
        assert logout_response.json()["message"] == "Successfully logged out"


class TestCrossModuleIntegration:
    """Test integration across multiple modules"""

    def test_health_to_workout_recommendation(self, client):
        """Test: Health data → Readiness score → Appropriate workout plan"""

        # Step 1: Register user
        register_response = client.post(
            "/auth/register",
            json={"email": "cross1@example.com", "password": "CrossPass123!"}
        )
        access_token = register_response.json()["access_token"]

        me_response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        user_id = str(me_response.json()["id"])

        # Step 2: Ingest poor sleep data (only 4 hours)
        yesterday = datetime.utcnow() - timedelta(hours=20)
        poor_sleep = {
            "samples": [{
                "user_id": user_id,
                "sample_type": "sleep_stage",
                "value": 1.0,
                "start_time": yesterday.isoformat(),
                "end_time": (yesterday + timedelta(hours=4)).isoformat(),
                "source_uuid": "poor-sleep-1"
            }]
        }
        client.post(
            "/health/samples",
            json=poor_sleep,
            headers={"Authorization": f"Bearer {access_token}"}
        )

        # Step 3: Check readiness - should be low
        readiness_response = client.get(f"/readiness?user_id={user_id}")
        readiness = readiness_response.json()

        # Poor sleep should result in lower sleep score
        assert readiness["sleep_hours"] is not None
        assert readiness["scores"]["sleep"] < 0.6  # Less than 6/8 target

        # Step 4: Create light workout plan (appropriate for low readiness)
        today = str(date.today())
        light_plan = {
            "user_id": user_id,
            "date": today,
            "plan_json": {
                "warmup": ["Light walk"],
                "main": ["Mobility work", "Light stretching"],
                "cooldown": ["Meditation"],
                "notes": "Recovery day due to poor sleep"
            },
            "status": "pending"
        }
        plan_response = client.put(
            f"/daily-plans/{user_id}/{today}",
            json=light_plan,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert plan_response.status_code == 200

        # Step 5: Verify integrated data
        # Can retrieve both readiness and plan
        assert readiness_response.status_code == 200
        assert plan_response.status_code == 200


class TestErrorHandlingIntegration:
    """Test error handling across integrated workflows"""

    def test_unauthorized_access_workflow(self, client):
        """Test: User A cannot access User B's data"""

        # Create User A
        user_a_response = client.post(
            "/auth/register",
            json={"email": "usera@example.com", "password": "UserAPass123!"}
        )
        user_a_token = user_a_response.json()["access_token"]
        user_a_me = client.get("/auth/me", headers={"Authorization": f"Bearer {user_a_token}"})
        user_a_id = str(user_a_me.json()["id"])

        # Create User B
        user_b_response = client.post(
            "/auth/register",
            json={"email": "userb@example.com", "password": "UserBPass123!"}
        )
        user_b_token = user_b_response.json()["access_token"]
        user_b_me = client.get("/auth/me", headers={"Authorization": f"Bearer {user_b_token}"})
        user_b_id = str(user_b_me.json()["id"])

        # User B creates a workout plan
        today = str(date.today())
        user_b_plan = {
            "user_id": user_b_id,
            "date": today,
            "plan_json": {
                "warmup": ["Secret warmup"],
                "main": ["Secret workout"],
                "cooldown": ["Secret cooldown"],
                "notes": "User B's private plan"
            },
            "status": "pending"
        }
        create_response = client.put(
            f"/daily-plans/{user_b_id}/{today}",
            json=user_b_plan,
            headers={"Authorization": f"Bearer {user_b_token}"}
        )
        assert create_response.status_code == 200

        # User A tries to access User B's plan - should be forbidden
        forbidden_response = client.get(
            f"/daily-plans/{user_b_id}/{today}",
            headers={"Authorization": f"Bearer {user_a_token}"}
        )
        assert forbidden_response.status_code == 403

        # User A can access their own plan
        user_a_plan = {
            "user_id": user_a_id,
            "date": today,
            "plan_json": {
                "warmup": [],
                "main": [],
                "cooldown": [],
                "notes": ""
            },
            "status": "pending"
        }
        client.put(
            f"/daily-plans/{user_a_id}/{today}",
            json=user_a_plan,
            headers={"Authorization": f"Bearer {user_a_token}"}
        )

        own_response = client.get(
            f"/daily-plans/{user_a_id}/{today}",
            headers={"Authorization": f"Bearer {user_a_token}"}
        )
        assert own_response.status_code == 200
