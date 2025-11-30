"""
Comprehensive test suite for Workout Planner FastAPI backend
Tests goals, health samples, readiness, and deduplication logic
"""
import pytest
from fastapi.testclient import TestClient
from main import app
from database import init_sqlite, DATABASE_URL
import os
import sqlite3

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db():
    """Reset database before each test"""
    # Use test database
    test_db = "fitness_test.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    
    # Temporarily override DATABASE_URL before importing
    import sys
    import database
    original_url = database.DATABASE_URL
    database.DATABASE_URL = f"sqlite:///{test_db}"
    
    # Force re-initialization with new path
    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            goal_type TEXT NOT NULL,
            target_value REAL,
            target_unit TEXT,
            target_date TEXT,
            notes TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS goal_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (goal_id) REFERENCES user_goals(id)
        );

        CREATE TABLE IF NOT EXISTS health_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            sample_type TEXT NOT NULL,
            value REAL,
            unit TEXT,
            start_time TEXT,
            end_time TEXT,
            source_app TEXT,
            source_uuid TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_goal_plans_goal_id ON goal_plans(goal_id);
        CREATE INDEX IF NOT EXISTS idx_goal_plans_user_id ON goal_plans(user_id);
        CREATE INDEX IF NOT EXISTS idx_health_samples_user_id ON health_samples(user_id);
        CREATE INDEX IF NOT EXISTS idx_health_samples_type_time ON health_samples(sample_type, start_time);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_health_samples_dedupe ON health_samples(user_id, sample_type, start_time, source_uuid);
    """)
    conn.commit()
    conn.close()
    
    yield
    
    # Cleanup
    database.DATABASE_URL = original_url
    if os.path.exists(test_db):
        os.remove(test_db)


class TestGoalsAPI:
    """Test goals CRUD operations with target_unit support"""
    
    def test_create_goal_with_unit(self):
        """Test creating a goal with target value and unit"""
        response = client.post("/goals", json={
            "user_id": "test-user",
            "goal_type": "Marathon PR",
            "target_value": 26.2,
            "target_unit": "mi",
            "target_date": "2025-12-31",
            "notes": "Sub-4 hour goal"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["goal_type"] == "Marathon PR"
        assert data["target_value"] == 26.2
        assert data["target_unit"] == "mi"
        assert "id" in data
    
    def test_create_goal_without_unit(self):
        """Test creating a goal without target value/unit"""
        response = client.post("/goals", json={
            "user_id": "test-user",
            "goal_type": "General Fitness",
            "notes": "Stay consistent"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["goal_type"] == "General Fitness"
        assert data["target_value"] is None
        assert data["target_unit"] is None
    
    def test_update_goal_unit(self):
        """Test updating goal target and unit"""
        # Create goal
        create_response = client.post("/goals", json={
            "user_id": "test-user",
            "goal_type": "5K Race",
            "target_value": 5.0,
            "target_unit": "k"
        })
        goal_id = create_response.json()["id"]
        
        # Update to miles
        update_response = client.put(f"/goals/{goal_id}", json={
            "target_value": 3.1,
            "target_unit": "mi"
        })
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["target_value"] == 3.1
        assert data["target_unit"] == "mi"
    
    def test_list_goals(self):
        """Test listing all goals for a user"""
        # Create multiple goals
        client.post("/goals", json={"user_id": "test-user", "goal_type": "Goal 1"})
        client.post("/goals", json={"user_id": "test-user", "goal_type": "Goal 2"})
        client.post("/goals", json={"user_id": "other-user", "goal_type": "Goal 3"})
        
        # List for test-user
        response = client.get("/goals?user_id=test-user")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(g["user_id"] == "test-user" for g in data)
    
    def test_delete_goal(self):
        """Test soft-deleting a goal"""
        # Create goal
        create_response = client.post("/goals", json={
            "user_id": "test-user",
            "goal_type": "Test Goal"
        })
        goal_id = create_response.json()["id"]
        
        # Delete
        delete_response = client.delete(f"/goals/{goal_id}")
        assert delete_response.status_code == 200
        
        # Verify it's inactive (SQLite returns 0 for FALSE)
        get_response = client.get(f"/goals/{goal_id}")
        assert get_response.json()["is_active"] in [False, 0]


class TestGoalPlansAPI:
    """Test goal plans CRUD"""
    
    def test_create_plan(self):
        """Test creating a goal plan"""
        # First create a goal
        goal_response = client.post("/goals", json={
            "user_id": "test-user",
            "goal_type": "Ironman Training"
        })
        goal_id = goal_response.json()["id"]
        
        # Create plan
        plan_response = client.post("/goals/plans", json={
            "goal_id": goal_id,
            "user_id": "test-user",
            "name": "12-week Build",
            "description": "Base phase training"
        })
        assert plan_response.status_code == 200
        data = plan_response.json()
        assert data["name"] == "12-week Build"
        assert data["goal_id"] == goal_id
    
    def test_list_plans_for_goal(self):
        """Test listing plans for a specific goal"""
        # Create goal
        goal_response = client.post("/goals", json={
            "user_id": "test-user",
            "goal_type": "Test Goal"
        })
        goal_id = goal_response.json()["id"]
        
        # Create multiple plans
        client.post("/goals/plans", json={
            "goal_id": goal_id,
            "user_id": "test-user",
            "name": "Plan 1"
        })
        client.post("/goals/plans", json={
            "goal_id": goal_id,
            "user_id": "test-user",
            "name": "Plan 2"
        })
        
        # List plans
        response = client.get(f"/goals/{goal_id}/plans")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


class TestHealthAPI:
    """Test health samples ingestion and deduplication"""
    
    def test_ingest_single_sample(self):
        """Test ingesting a single health sample"""
        response = client.post("/health/samples", json={
            "samples": [{
                "user_id": "test-user",
                "sample_type": "heart_rate",
                "value": 72.0,
                "unit": "bpm",
                "start_time": "2025-11-16T08:00:00Z",
                "end_time": "2025-11-16T08:00:00Z",
                "source_app": "apple.health",
                "source_uuid": "uuid-hr-001"
            }]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["inserted"] == 1
        assert data["total"] == 1
    
    def test_deduplication(self):
        """Test that duplicate samples are ignored"""
        sample = {
            "user_id": "test-user",
            "sample_type": "workout_distance",
            "value": 5000.0,
            "unit": "m",
            "start_time": "2025-11-16T07:00:00Z",
            "end_time": "2025-11-16T08:00:00Z",
            "source_app": "apple.health",
            "source_uuid": "uuid-workout-001"
        }
        
        # Insert first time
        response1 = client.post("/health/samples", json={"samples": [sample]})
        assert response1.json()["inserted"] == 1
        
        # Insert same sample again
        response2 = client.post("/health/samples", json={"samples": [sample]})
        # Should not insert duplicate
        assert response2.json()["inserted"] == 0
        
        # Verify only one sample exists
        list_response = client.get("/health/samples?user_id=test-user&sample_type=workout_distance")
        assert len(list_response.json()) == 1
    
    def test_batch_ingest(self):
        """Test ingesting multiple samples in batch"""
        samples = [
            {
                "user_id": "test-user",
                "sample_type": "hrv",
                "value": 45.0 + i,
                "unit": "ms",
                "start_time": f"2025-11-{10+i:02d}T08:00:00Z",
                "end_time": f"2025-11-{10+i:02d}T08:00:00Z",
                "source_app": "apple.health",
                "source_uuid": f"uuid-hrv-{i:03d}"
            }
            for i in range(10)
        ]
        
        response = client.post("/health/samples", json={"samples": samples})
        assert response.status_code == 200
        data = response.json()
        assert data["inserted"] == 10
        assert data["total"] == 10
    
    def test_list_samples(self):
        """Test listing samples with filters"""
        # Ingest mixed samples
        client.post("/health/samples", json={"samples": [
            {
                "user_id": "test-user",
                "sample_type": "heart_rate",
                "value": 70.0,
                "unit": "bpm",
                "start_time": "2025-11-16T08:00:00Z",
                "end_time": "2025-11-16T08:00:00Z",
                "source_uuid": "uuid-1"
            },
            {
                "user_id": "test-user",
                "sample_type": "sleep_stage",
                "value": 2.0,
                "unit": "code",
                "start_time": "2025-11-16T00:00:00Z",
                "end_time": "2025-11-16T01:00:00Z",
                "source_uuid": "uuid-2"
            }
        ]})
        
        # List only heart_rate
        response = client.get("/health/samples?user_id=test-user&sample_type=heart_rate")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["sample_type"] == "heart_rate"
    
    def test_summary(self):
        """Test health summary aggregation"""
        # Ingest samples
        client.post("/health/samples", json={"samples": [
            {
                "user_id": "test-user",
                "sample_type": "workout_calories",
                "value": 500.0,
                "unit": "kcal",
                "start_time": f"2025-11-{10+i:02d}T07:00:00Z",
                "end_time": f"2025-11-{10+i:02d}T08:00:00Z",
                "source_uuid": f"uuid-cal-{i}"
            }
            for i in range(5)
        ]})
        
        # Get summary
        response = client.get("/health/summary?user_id=test-user")
        assert response.status_code == 200
        data = response.json()
        assert "workout_calories" in data
        assert data["workout_calories"]["count"] == 5
        assert data["workout_calories"]["total"] == 2500.0


class TestReadinessAPI:
    """Test readiness calculation endpoint"""
    
    def test_readiness_with_data(self):
        """Test readiness calculation with actual health data"""
        # Ingest HRV samples (recent + baseline)
        hrv_samples = [
            {
                "user_id": "test-user",
                "sample_type": "hrv",
                "value": 50.0,
                "unit": "ms",
                "start_time": "2025-11-16T08:00:00Z",  # Recent (yesterday)
                "end_time": "2025-11-16T08:00:00Z",
                "source_uuid": f"hrv-recent"
            }
        ] + [
            {
                "user_id": "test-user",
                "sample_type": "hrv",
                "value": 45.0,
                "unit": "ms",
                "start_time": f"2025-11-{i:02d}T08:00:00Z",  # Baseline
                "end_time": f"2025-11-{i:02d}T08:00:00Z",
                "source_uuid": f"hrv-baseline-{i}"
            }
            for i in range(1, 15)
        ]
        
        # Ingest resting HR
        resting_samples = [
            {
                "user_id": "test-user",
                "sample_type": "resting_hr",
                "value": 55.0,
                "unit": "bpm",
                "start_time": "2025-11-16T08:00:00Z",
                "end_time": "2025-11-16T08:00:00Z",
                "source_uuid": "rhr-recent"
            }
        ] + [
            {
                "user_id": "test-user",
                "sample_type": "resting_hr",
                "value": 60.0,
                "unit": "bpm",
                "start_time": f"2025-11-{i:02d}T08:00:00Z",
                "end_time": f"2025-11-{i:02d}T08:00:00Z",
                "source_uuid": f"rhr-baseline-{i}"
            }
            for i in range(1, 15)
        ]
        
        # Ingest sleep
        sleep_samples = [
            {
                "user_id": "test-user",
                "sample_type": "sleep_stage",
                "value": 2.0,
                "unit": "code",
                "start_time": "2025-11-15T22:00:00Z",
                "end_time": "2025-11-16T06:00:00Z",  # 8 hours
                "source_uuid": "sleep-recent"
            }
        ]
        
        client.post("/health/samples", json={"samples": hrv_samples + resting_samples + sleep_samples})
        
        # Get readiness
        response = client.get("/readiness?user_id=test-user")
        assert response.status_code == 200
        data = response.json()
        
        assert "readiness" in data
        assert 0.0 <= data["readiness"] <= 1.0
        assert "hrv" in data
        assert "resting_hr" in data
        assert "sleep_hours" in data
    
    def test_readiness_no_data(self):
        """Test readiness returns default values when no data available"""
        response = client.get("/readiness?user_id=nonexistent-user")
        assert response.status_code == 200
        data = response.json()
        # With no data, readiness may return non-zero baseline values
        assert "readiness" in data
        assert "hrv" in data
        assert "sleep_hours" in data


class TestIntegration:
    """Integration tests combining multiple features"""
    
    def test_full_workflow(self):
        """Test complete user workflow: create goal, ingest health data, check readiness"""
        # 1. Create a goal
        goal_response = client.post("/goals", json={
            "user_id": "integration-user",
            "goal_type": "Improve Readiness",
            "target_value": 0.8,
            "target_unit": "score",
            "notes": "Target 80% readiness average"
        })
        assert goal_response.status_code == 200
        goal_id = goal_response.json()["id"]
        
        # 2. Ingest health data
        health_response = client.post("/health/samples", json={"samples": [
            {
                "user_id": "integration-user",
                "sample_type": "hrv",
                "value": 55.0,
                "unit": "ms",
                "start_time": "2025-11-16T08:00:00Z",
                "end_time": "2025-11-16T08:00:00Z",
                "source_uuid": "int-hrv-1"
            },
            {
                "user_id": "integration-user",
                "sample_type": "workout_distance",
                "value": 5000.0,
                "unit": "m",
                "start_time": "2025-11-15T07:00:00Z",
                "end_time": "2025-11-15T08:00:00Z",
                "source_uuid": "int-workout-1"
            }
        ]})
        assert health_response.status_code == 200
        
        # 3. Check readiness
        readiness_response = client.get("/readiness?user_id=integration-user")
        assert readiness_response.status_code == 200
        
        # 4. Get health summary
        summary_response = client.get("/health/summary?user_id=integration-user")
        assert summary_response.status_code == 200
        summary = summary_response.json()
        assert "workout_distance" in summary
        
        # 5. Verify goal still exists
        goals_response = client.get("/goals?user_id=integration-user")
        assert len(goals_response.json()) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
