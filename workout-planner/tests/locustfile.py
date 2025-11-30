"""
Load testing scenarios for Workout Planner API using Locust.

Run with:
    locust -f tests/locustfile.py --host=http://localhost:8000

For headless mode with 100 users ramping up over 10 seconds:
    locust -f tests/locustfile.py --host=http://localhost:8000 --users 100 --spawn-rate 10 --run-time 2m --headless
"""

import json
import random
import uuid
from datetime import datetime, timedelta
from locust import HttpUser, task, between, SequentialTaskSet


class AuthenticationFlow(SequentialTaskSet):
    """Test authentication endpoints under load"""

    @task
    def register_user(self):
        """Register a new user"""
        email = f"load_test_{uuid.uuid4().hex[:8]}@example.com"
        password = "LoadTest123!"

        with self.client.post(
            "/auth/register",
            json={"email": email, "password": password},
            catch_response=True
        ) as response:
            if response.status_code == 201:
                data = response.json()
                self.user.access_token = data.get("access_token")
                self.user.refresh_token = data.get("refresh_token")
                self.user.user_id = None  # Will get from /auth/me
                response.success()
            else:
                response.failure(f"Registration failed with status {response.status_code}")

    @task
    def get_user_profile(self):
        """Get current user profile to retrieve user_id"""
        if not hasattr(self.user, 'access_token'):
            return

        with self.client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {self.user.access_token}"},
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.user.user_id = str(data.get("id"))
                response.success()
            else:
                response.failure(f"Get profile failed with status {response.status_code}")

    @task
    def refresh_token(self):
        """Refresh access token"""
        if not hasattr(self.user, 'refresh_token'):
            return

        with self.client.post(
            "/auth/refresh",
            json={"refresh_token": self.user.refresh_token},
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.user.access_token = data.get("access_token")
                response.success()
            else:
                response.failure(f"Token refresh failed with status {response.status_code}")


class WorkoutPlanWorkflow(SequentialTaskSet):
    """Test workout plan CRUD operations under load"""

    def on_start(self):
        """Ensure user is authenticated before starting workout plan operations"""
        if not hasattr(self.user, 'access_token') or not hasattr(self.user, 'user_id'):
            # Quick auth setup
            email = f"workout_user_{uuid.uuid4().hex[:8]}@example.com"
            response = self.client.post("/auth/register", json={"email": email, "password": "Test123!"})
            if response.status_code == 201:
                data = response.json()
                self.user.access_token = data["access_token"]
                # Get user_id
                me_response = self.client.get("/auth/me", headers={"Authorization": f"Bearer {self.user.access_token}"})
                if me_response.status_code == 200:
                    self.user.user_id = str(me_response.json()["id"])

    @task(3)
    def get_daily_plan(self):
        """Retrieve daily workout plan (most common operation)"""
        if not hasattr(self.user, 'user_id'):
            return

        today = datetime.now().date().isoformat()
        headers = {"Authorization": f"Bearer {self.user.access_token}"}

        with self.client.get(
            f"/daily-plans/{self.user.user_id}/{today}",
            headers=headers,
            name="/daily-plans/[user_id]/[date]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get daily plan failed: {response.status_code}")

    @task(2)
    def save_daily_plan(self):
        """Save/update daily workout plan"""
        if not hasattr(self.user, 'user_id'):
            return

        today = datetime.now().date().isoformat()
        headers = {"Authorization": f"Bearer {self.user.access_token}"}

        plan_content = [
            {"line_num": 1, "text": "Morning Run - 5k"},
            {"line_num": 2, "text": "Afternoon Strength Training"},
            {"line_num": 3, "text": "Evening Yoga - 30min"}
        ]

        with self.client.post(
            f"/daily-plans/{self.user.user_id}/{today}",
            headers=headers,
            json={"lines": plan_content},
            name="/daily-plans/[user_id]/[date] POST",
            catch_response=True
        ) as response:
            if response.status_code in [200, 201]:
                response.success()
            else:
                response.failure(f"Save daily plan failed: {response.status_code}")

    @task(2)
    def get_weekly_plan(self):
        """Retrieve weekly workout plan"""
        if not hasattr(self.user, 'user_id'):
            return

        headers = {"Authorization": f"Bearer {self.user.access_token}"}

        with self.client.get(
            f"/weekly-plans/{self.user.user_id}",
            headers=headers,
            name="/weekly-plans/[user_id]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get weekly plan failed: {response.status_code}")

    @task(1)
    def save_weekly_plan(self):
        """Save/update weekly workout plan"""
        if not hasattr(self.user, 'user_id'):
            return

        headers = {"Authorization": f"Bearer {self.user.access_token}"}

        weekly_plan = {
            "user_id": self.user.user_id,
            "focus": random.choice(["strength", "endurance", "balanced", "recovery"]),
            "notes": "Load test weekly plan"
        }

        with self.client.post(
            f"/weekly-plans/{self.user.user_id}",
            headers=headers,
            json=weekly_plan,
            name="/weekly-plans/[user_id] POST",
            catch_response=True
        ) as response:
            if response.status_code in [200, 201]:
                response.success()
            else:
                response.failure(f"Save weekly plan failed: {response.status_code}")


class HealthDataWorkflow(SequentialTaskSet):
    """Test health data ingestion and readiness calculation under load"""

    def on_start(self):
        """Setup authentication"""
        if not hasattr(self.user, 'access_token') or not hasattr(self.user, 'user_id'):
            email = f"health_user_{uuid.uuid4().hex[:8]}@example.com"
            response = self.client.post("/auth/register", json={"email": email, "password": "Test123!"})
            if response.status_code == 201:
                data = response.json()
                self.user.access_token = data["access_token"]
                me_response = self.client.get("/auth/me", headers={"Authorization": f"Bearer {self.user.access_token}"})
                if me_response.status_code == 200:
                    self.user.user_id = str(me_response.json()["id"])

    @task(3)
    def ingest_health_samples(self):
        """Ingest health data samples (high frequency operation)"""
        if not hasattr(self.user, 'user_id'):
            return

        headers = {"Authorization": f"Bearer {self.user.access_token}"}
        now = datetime.utcnow().isoformat()

        # Simulate batch of health samples from wearable device
        samples = {
            "samples": [
                {
                    "user_id": self.user.user_id,
                    "sample_type": "hrv",
                    "value": random.uniform(40, 80),
                    "unit": "ms",
                    "start_time": now,
                    "end_time": now,
                    "source_uuid": f"locust-hrv-{uuid.uuid4()}"
                },
                {
                    "user_id": self.user.user_id,
                    "sample_type": "resting_hr",
                    "value": random.uniform(50, 80),
                    "unit": "bpm",
                    "start_time": now,
                    "end_time": now,
                    "source_uuid": f"locust-hr-{uuid.uuid4()}"
                },
                {
                    "user_id": self.user.user_id,
                    "sample_type": "steps",
                    "value": random.uniform(0, 500),
                    "unit": "count",
                    "start_time": now,
                    "end_time": now,
                    "source_uuid": f"locust-steps-{uuid.uuid4()}"
                }
            ]
        }

        with self.client.post(
            "/health/samples",
            headers=headers,
            json=samples,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Ingest samples failed: {response.status_code}")

    @task(2)
    def get_readiness_score(self):
        """Calculate readiness score from health data"""
        if not hasattr(self.user, 'user_id'):
            return

        with self.client.get(
            f"/readiness?user_id={self.user.user_id}",
            name="/readiness",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                # Verify response structure
                if "readiness" in data and "scores" in data:
                    response.success()
                else:
                    response.failure("Invalid readiness response structure")
            else:
                response.failure(f"Get readiness failed: {response.status_code}")

    @task(1)
    def list_health_samples(self):
        """Query health samples"""
        if not hasattr(self.user, 'user_id'):
            return

        headers = {"Authorization": f"Bearer {self.user.access_token}"}

        with self.client.get(
            f"/health/samples?user_id={self.user.user_id}&limit=50",
            headers=headers,
            name="/health/samples",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"List samples failed: {response.status_code}")


class MealsWorkflow(SequentialTaskSet):
    """Test meal planning endpoints under load"""

    def on_start(self):
        """Setup authentication"""
        if not hasattr(self.user, 'access_token') or not hasattr(self.user, 'user_id'):
            email = f"meals_user_{uuid.uuid4().hex[:8]}@example.com"
            response = self.client.post("/auth/register", json={"email": email, "password": "Test123!"})
            if response.status_code == 201:
                data = response.json()
                self.user.access_token = data["access_token"]
                me_response = self.client.get("/auth/me", headers={"Authorization": f"Bearer {self.user.access_token}"})
                if me_response.status_code == 200:
                    self.user.user_id = str(me_response.json()["id"])

    @task
    def get_weekly_meal_plan(self):
        """Get weekly meal plan"""
        if not hasattr(self.user, 'user_id'):
            return

        headers = {"Authorization": f"Bearer {self.user.access_token}"}

        with self.client.get(
            f"/meals/weekly-plan/{self.user.user_id}",
            headers=headers,
            name="/meals/weekly-plan/[user_id]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get meal plan failed: {response.status_code}")


class workout-plannerUser(HttpUser):
    """
    Simulated user of the Workout Planner API.

    This user randomly performs different workflows with realistic wait times.
    """

    # Wait between 1-5 seconds between tasks (simulating human behavior)
    wait_time = between(1, 5)

    # Weight distribution: users spend more time on workout plans than other features
    tasks = {
        WorkoutPlanWorkflow: 5,
        HealthDataWorkflow: 3,
        AuthenticationFlow: 1,
        MealsWorkflow: 2
    }

    def on_start(self):
        """Initialize user session"""
        self.access_token = None
        self.refresh_token = None
        self.user_id = None


class HealthMonitoringUser(HttpUser):
    """
    User focused on health data tracking and readiness monitoring.

    Simulates users who primarily use health tracking features.
    """

    wait_time = between(2, 8)

    tasks = {
        HealthDataWorkflow: 10,
        WorkoutPlanWorkflow: 2
    }

    def on_start(self):
        """Initialize user session"""
        self.access_token = None
        self.user_id = None


class CasualUser(HttpUser):
    """
    Casual user who occasionally checks plans and logs data.

    Simulates low-frequency users with longer wait times.
    """

    wait_time = between(5, 15)

    tasks = {
        WorkoutPlanWorkflow: 3,
        MealsWorkflow: 2,
        HealthDataWorkflow: 1
    }

    def on_start(self):
        """Initialize user session"""
        self.access_token = None
        self.user_id = None
