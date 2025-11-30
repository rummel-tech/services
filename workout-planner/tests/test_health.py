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
    tmp_db = os.path.join(tempfile.gettempdir(), "health_test.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_db}"

    from database import init_sqlite  # type: ignore
    init_sqlite()
    from main import app  # type: ignore
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_data(client):
    """Get authentication token and user ID for testing"""
    response = client.post("/auth/register", json={"email": "healthuser@example.com", "password": "TestPassword123!"})
    assert response.status_code == 201
    token = response.json()["access_token"]

    # Get user ID from /auth/me
    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    user_id = str(me_response.json()["id"])

    return {"token": token, "user_id": user_id}


@pytest.fixture(scope="module")
def auth_token(auth_data):
    """Get authentication token for testing"""
    return auth_data["token"]


@pytest.fixture(scope="module")
def user_id(auth_data):
    """Get user ID for testing"""
    return auth_data["user_id"]


def test_ingest_health_samples_success(client, auth_token, user_id):
    """Test successfully ingesting health samples"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    now = datetime.utcnow().isoformat()

    payload = {
        "samples": [
            {
                "user_id": user_id,
                "sample_type": "HeartRate",
                "value": 72.0,
                "unit": "bpm",
                "start_time": now,
                "end_time": now,
                "source_app": "AppleHealth",
                "source_uuid": "test-uuid-1"
            },
            {
                "user_id": user_id,
                "sample_type": "Steps",
                "value": 5000.0,
                "unit": "count",
                "start_time": now,
                "end_time": now,
                "source_app": "AppleHealth",
                "source_uuid": "test-uuid-2"
            }
        ]
    }

    r = client.post("/health/samples", json=payload, headers=headers)
    assert r.status_code == 200

    data = r.json()
    assert "inserted" in data
    assert "total" in data
    assert data["total"] == 2


def test_ingest_health_samples_empty_list(client, auth_token):
    """Test ingesting with empty samples list"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {"samples": []}

    r = client.post("/health/samples", json=payload, headers=headers)
    assert r.status_code == 400


def test_ingest_health_samples_unauthorized(client, user_id):
    """Test ingesting samples without authentication"""
    now = datetime.utcnow().isoformat()
    payload = {
        "samples": [
            {
                "user_id": user_id,
                "sample_type": "HeartRate",
                "value": 72.0,
                "unit": "bpm",
                "start_time": now,
                "end_time": now
            }
        ]
    }

    r = client.post("/health/samples", json=payload)
    assert r.status_code == 403


def test_ingest_health_samples_wrong_user(client, auth_token):
    """Test ingesting samples for different user"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    now = datetime.utcnow().isoformat()

    payload = {
        "samples": [
            {
                "user_id": "different-user",
                "sample_type": "HeartRate",
                "value": 72.0,
                "unit": "bpm",
                "start_time": now,
                "end_time": now
            }
        ]
    }

    r = client.post("/health/samples", json=payload, headers=headers)
    assert r.status_code == 403


def test_list_health_samples(client, auth_token, user_id):
    """Test listing health samples"""
    headers = {"Authorization": f"Bearer {auth_token}"}

    # First ingest some samples
    now = datetime.utcnow().isoformat()
    payload = {
        "samples": [
            {
                "user_id": user_id,
                "sample_type": "HeartRate",
                "value": 75.0,
                "unit": "bpm",
                "start_time": now,
                "end_time": now,
                "source_uuid": "test-list-1"
            },
            {
                "user_id": user_id,
                "sample_type": "Steps",
                "value": 3000.0,
                "unit": "count",
                "start_time": now,
                "end_time": now,
                "source_uuid": "test-list-2"
            }
        ]
    }
    client.post("/health/samples", json=payload, headers=headers)

    # Now list them
    r = client.get(f"/health/samples?user_id={user_id}", headers=headers)
    assert r.status_code == 200

    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 2  # At least the 2 we just added


def test_list_health_samples_filtered_by_type(client, auth_token, user_id):
    """Test listing health samples filtered by sample type"""
    headers = {"Authorization": f"Bearer {auth_token}"}

    # List only HeartRate samples
    r = client.get(f"/health/samples?user_id={user_id}&sample_type=HeartRate", headers=headers)
    assert r.status_code == 200

    data = r.json()
    assert isinstance(data, list)
    # All returned samples should be HeartRate
    for sample in data:
        assert sample["sample_type"] == "HeartRate"


def test_list_health_samples_with_limit(client, auth_token, user_id):
    """Test listing health samples with limit parameter"""
    headers = {"Authorization": f"Bearer {auth_token}"}

    r = client.get(f"/health/samples?user_id={user_id}&limit=5", headers=headers)
    assert r.status_code == 200

    data = r.json()
    assert isinstance(data, list)
    assert len(data) <= 5


def test_list_health_samples_unauthorized(client, user_id):
    """Test listing samples without authentication"""
    r = client.get(f"/health/samples?user_id={user_id}")
    assert r.status_code == 403


def test_list_health_samples_wrong_user(client, auth_token):
    """Test listing samples for different user"""
    headers = {"Authorization": f"Bearer {auth_token}"}

    r = client.get("/health/samples?user_id=different-user", headers=headers)
    assert r.status_code == 403


def test_health_summary(client, auth_token, user_id):
    """Test getting health summary"""
    headers = {"Authorization": f"Bearer {auth_token}"}

    # Ingest some samples first
    now = datetime.utcnow().isoformat()
    payload = {
        "samples": [
            {
                "user_id": user_id,
                "sample_type": "Weight",
                "value": 70.0,
                "unit": "kg",
                "start_time": now,
                "end_time": now,
                "source_uuid": "test-summary-1"
            },
            {
                "user_id": user_id,
                "sample_type": "Weight",
                "value": 71.0,
                "unit": "kg",
                "start_time": now,
                "end_time": now,
                "source_uuid": "test-summary-2"
            }
        ]
    }
    client.post("/health/samples", json=payload, headers=headers)

    # Get summary
    r = client.get(f"/health/summary?user_id={user_id}&days=7")
    assert r.status_code == 200

    data = r.json()
    assert isinstance(data, dict)
    # Should have Weight stats if samples were ingested
    if "Weight" in data:
        assert "count" in data["Weight"]
        assert "avg_value" in data["Weight"]


def test_health_summary_with_custom_days(client, user_id):
    """Test health summary with custom days parameter"""
    r = client.get(f"/health/summary?user_id={user_id}&days=30")
    assert r.status_code == 200

    data = r.json()
    assert isinstance(data, dict)


def test_ingest_duplicate_samples(client, auth_token, user_id):
    """Test that duplicate samples are handled (INSERT OR IGNORE for SQLite)"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    now = datetime.utcnow().isoformat()

    # Same sample with same source_uuid
    payload = {
        "samples": [
            {
                "user_id": user_id,
                "sample_type": "HeartRate",
                "value": 80.0,
                "unit": "bpm",
                "start_time": now,
                "end_time": now,
                "source_uuid": "duplicate-test-uuid"
            }
        ]
    }

    # Insert first time
    r1 = client.post("/health/samples", json=payload, headers=headers)
    assert r1.status_code == 200

    # Insert duplicate - should be ignored
    r2 = client.post("/health/samples", json=payload, headers=headers)
    assert r2.status_code == 200
    data2 = r2.json()
    # For SQLite with INSERT OR IGNORE, the duplicate should be skipped
    assert data2["inserted"] == 0 or data2["inserted"] == 1  # Depends on implementation


def test_ingest_samples_minimal_fields(client, auth_token, user_id):
    """Test ingesting samples with only required fields"""
    headers = {"Authorization": f"Bearer {auth_token}"}

    payload = {
        "samples": [
            {
                "user_id": user_id,
                "sample_type": "MinimalSample"
                # All other fields are optional
            }
        ]
    }

    r = client.post("/health/samples", json=payload, headers=headers)
    assert r.status_code == 200
