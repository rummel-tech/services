import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Ensure path includes server root so imports resolve
    test_file = Path(__file__).resolve()
    server_root = test_file.parents[1]  # python_fastapi_server directory
    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))

    # Isolated SQLite DB for these tests
    tmp_db = os.path.join(tempfile.gettempdir(), "readiness_test.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_db}"

    from database import init_sqlite  # type: ignore
    init_sqlite()
    from main import app  # type: ignore
    return TestClient(app)


@pytest.fixture(scope="function")
def auth_data(client):
    """Get authentication token and user ID for testing - function scoped for isolation"""
    import uuid
    email = f"readiness_{uuid.uuid4().hex[:8]}@example.com"
    response = client.post("/auth/register", json={"email": email, "password": "TestPassword123!"})
    assert response.status_code == 201
    token = response.json()["access_token"]

    # Get user ID from /auth/me
    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    user_id = str(me_response.json()["id"])

    return {"token": token, "user_id": user_id}


@pytest.fixture(scope="function")
def auth_token(auth_data):
    """Get authentication token for testing"""
    return auth_data["token"]


@pytest.fixture(scope="function")
def user_id(auth_data):
    """Get user ID for testing"""
    return auth_data["user_id"]


def test_readiness_no_data(client, user_id):
    """Test readiness score with no health data"""
    r = client.get(f"/readiness?user_id={user_id}")
    assert r.status_code == 200

    data = r.json()
    assert data["user_id"] == user_id
    assert "readiness" in data
    assert "scores" in data
    assert "hrv" in data["scores"]
    assert "resting_hr" in data["scores"]
    assert "sleep" in data["scores"]

    # With no data, scores should be 0.5 (neutral)
    assert data["scores"]["hrv"] == 0.5
    assert data["scores"]["resting_hr"] == 0.5
    assert data["scores"]["sleep"] == 0.5


def test_readiness_with_hrv_data(client, auth_token, user_id):
    """Test readiness score with HRV data"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    now = datetime.utcnow()

    # Add baseline HRV data (14 days ago)
    baseline_time = (now - timedelta(days=7)).isoformat()
    baseline_samples = {
        "samples": [
            {
                "user_id": user_id,
                "sample_type": "hrv",
                "value": 50.0,
                "unit": "ms",
                "start_time": baseline_time,
                "end_time": baseline_time,
                "source_uuid": f"hrv-baseline-{i}"
            }
            for i in range(5)
        ]
    }
    client.post("/health/samples", json=baseline_samples, headers=headers)

    # Add recent HRV data (last 24 hours) - better than baseline
    recent_time = now.isoformat()
    recent_samples = {
        "samples": [
            {
                "user_id": user_id,
                "sample_type": "hrv",
                "value": 60.0,
                "unit": "ms",
                "start_time": recent_time,
                "end_time": recent_time,
                "source_uuid": f"hrv-recent-{i}"
            }
            for i in range(3)
        ]
    }
    client.post("/health/samples", json=recent_samples, headers=headers)

    # Get readiness score
    r = client.get(f"/readiness?user_id={user_id}")
    assert r.status_code == 200

    data = r.json()
    assert data["hrv"] == 60.0
    # Baseline should be close to 50.0 (within 10%)
    assert 45.0 <= data["hrv_baseline"] <= 55.0
    # HRV score should be > 0.5 since current is better than baseline
    assert data["scores"]["hrv"] > 0.5


def test_readiness_with_resting_hr_data(client, auth_token, user_id):
    """Test readiness score with resting heart rate data"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    now = datetime.utcnow()

    # Add baseline resting HR data
    baseline_time = (now - timedelta(days=7)).isoformat()
    baseline_samples = {
        "samples": [
            {
                "user_id": user_id,
                "sample_type": "resting_hr",
                "value": 60.0,
                "unit": "bpm",
                "start_time": baseline_time,
                "end_time": baseline_time,
                "source_uuid": f"hr-baseline-{i}"
            }
            for i in range(5)
        ]
    }
    client.post("/health/samples", json=baseline_samples, headers=headers)

    # Add recent resting HR data - lower is better (55 vs 60)
    recent_time = now.isoformat()
    recent_samples = {
        "samples": [
            {
                "user_id": user_id,
                "sample_type": "resting_hr",
                "value": 55.0,
                "unit": "bpm",
                "start_time": recent_time,
                "end_time": recent_time,
                "source_uuid": f"hr-recent-{i}"
            }
            for i in range(3)
        ]
    }
    client.post("/health/samples", json=recent_samples, headers=headers)

    # Get readiness score
    r = client.get(f"/readiness?user_id={user_id}")
    assert r.status_code == 200

    data = r.json()
    assert data["resting_hr"] == 55.0
    # Baseline should be close to 60.0 (within 10%)
    assert 54.0 <= data["resting_hr_baseline"] <= 66.0
    # Resting HR score should be > 0.5 since current is lower (better) than baseline
    assert data["scores"]["resting_hr"] >= 0.5


def test_readiness_with_sleep_data(client, auth_token, user_id):
    """Test readiness score with sleep data"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    now = datetime.utcnow()
    yesterday = now - timedelta(hours=20)

    # Add sleep data - 8 hours of sleep
    sleep_start = yesterday.isoformat()
    sleep_end = (yesterday + timedelta(hours=8)).isoformat()

    sleep_samples = {
        "samples": [
            {
                "user_id": user_id,
                "sample_type": "sleep_stage",
                "value": 1.0,
                "unit": "stage",
                "start_time": sleep_start,
                "end_time": sleep_end,
                "source_uuid": "sleep-test-1"
            }
        ]
    }
    client.post("/health/samples", json=sleep_samples, headers=headers)

    # Get readiness score
    r = client.get(f"/readiness?user_id={user_id}")
    assert r.status_code == 200

    data = r.json()
    # Should have ~8 hours of sleep
    assert data["sleep_hours"] is not None
    assert 7.5 <= data["sleep_hours"] <= 8.5
    # Sleep score should be ~1.0 (8 hours / 8 hours target)
    assert data["scores"]["sleep"] >= 0.9


def test_readiness_combined_score(client, user_id):
    """Test that readiness score is weighted combination of components"""
    r = client.get(f"/readiness?user_id={user_id}")
    assert r.status_code == 200

    data = r.json()
    assert "readiness" in data
    assert isinstance(data["readiness"], float)
    assert 0.0 <= data["readiness"] <= 1.0

    # Verify it's a weighted average (0.4 * hrv + 0.3 * resting + 0.3 * sleep)
    expected = round(
        data["scores"]["hrv"] * 0.4 +
        data["scores"]["resting_hr"] * 0.3 +
        data["scores"]["sleep"] * 0.3,
        3
    )
    assert data["readiness"] == expected


def test_readiness_window_times(client, user_id):
    """Test that window times are included in response"""
    r = client.get(f"/readiness?user_id={user_id}")
    assert r.status_code == 200

    data = r.json()
    assert "window" in data
    assert "day_start" in data["window"]
    assert "baseline_start" in data["window"]

    # Verify window times are ISO format strings
    from datetime import datetime
    datetime.fromisoformat(data["window"]["day_start"])
    datetime.fromisoformat(data["window"]["baseline_start"])


def test_readiness_response_structure(client, user_id):
    """Test complete response structure"""
    r = client.get(f"/readiness?user_id={user_id}")
    assert r.status_code == 200

    data = r.json()

    # Top level fields
    assert "user_id" in data
    assert "hrv" in data
    assert "hrv_baseline" in data
    assert "resting_hr" in data
    assert "resting_hr_baseline" in data
    assert "sleep_hours" in data
    assert "scores" in data
    assert "readiness" in data
    assert "window" in data

    # Scores structure
    assert "hrv" in data["scores"]
    assert "resting_hr" in data["scores"]
    assert "sleep" in data["scores"]

    # Window structure
    assert "day_start" in data["window"]
    assert "baseline_start" in data["window"]
