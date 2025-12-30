"""End-to-end scenario test covering multi-feature flow.

Flow:
1. Create multiple goals
2. Ingest mixed health samples batch
3. Query readiness
4. Create chat session via sending first message
5. Send follow-up message reusing session
Assertions verify cross-feature consistency.
"""
import os
import sqlite3
from fastapi.testclient import TestClient
from main import app
import database

client = TestClient(app)

TEST_DB = "fitness_e2e.db"

def reset_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    database.DATABASE_URL = f"sqlite:///{TEST_DB}"
    # Initialize schema by calling init method indirectly via first request or direct script
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    # Minimal schema recreation (copied critical tables) — full schema lives in database.init_sqlite
    # We invoke main import which should create tables if missing; ensure chat tables exist
    from database import init_sqlite
    init_sqlite()
    conn.close()


def test_end_to_end_flow():
    reset_db()
    user_id = "user-e2e"

    # 1. Create goals
    goals_payload = [
        {"user_id": user_id, "goal_type": "5K Time", "target_value": 25.0, "target_unit": "min", "target_date": "2025-12-31"},
        {"user_id": user_id, "goal_type": "Weekly Distance", "target_value": 30.0, "target_unit": "km", "target_date": "2025-11-30"},
    ]
    created_goal_ids = []
    for g in goals_payload:
        r = client.post("/goals", json=g)
        assert r.status_code == 200, r.text
        created_goal_ids.append(r.json()["id"])

    # 2. Ingest health samples (distance + calories + hrv + resting_hr + heart_rate + sleep)
    samples = []
    # workout distance & calories
    samples.append({"user_id": user_id, "sample_type": "workout_distance", "value": 5000.0, "unit": "m", "start_time": "2025-11-16T08:00:00Z", "end_time": "2025-11-16T08:30:00Z", "source_app": "apple.health", "source_uuid": "w1"})
    samples.append({"user_id": user_id, "sample_type": "workout_calories", "value": 450.0, "unit": "kcal", "start_time": "2025-11-16T08:00:00Z", "end_time": "2025-11-16T08:30:00Z", "source_app": "apple.health", "source_uuid": "w1"})
    # HRV
    samples.append({"user_id": user_id, "sample_type": "hrv", "value": 55.0, "unit": "ms", "start_time": "2025-11-16T06:00:00Z", "end_time": "2025-11-16T06:05:00Z", "source_app": "apple.health", "source_uuid": "hrv1"})
    # Resting HR
    samples.append({"user_id": user_id, "sample_type": "resting_hr", "value": 50.0, "unit": "bpm", "start_time": "2025-11-16T06:00:00Z", "end_time": "2025-11-16T06:01:00Z", "source_app": "apple.health", "source_uuid": "rhr1"})
    # Heart rate workout samples
    for i in range(3):
        samples.append({"user_id": user_id, "sample_type": "heart_rate", "value": 120 + i, "unit": "bpm", "start_time": f"2025-11-16T08:0{i}:00Z", "end_time": f"2025-11-16T08:0{i}:10Z", "source_app": "apple.health", "source_uuid": f"hr{i}"})
    # Sleep stage sample
    samples.append({"user_id": user_id, "sample_type": "sleep_stage", "value": 3, "unit": "code", "start_time": "2025-11-16T00:00:00Z", "end_time": "2025-11-16T06:00:00Z", "source_app": "apple.health", "source_uuid": "sleep1"})

    ingest_resp = client.post("/health/samples", json={"samples": samples})
    assert ingest_resp.status_code == 200, ingest_resp.text
    ingest_data = ingest_resp.json()
    assert ingest_data["inserted"] == len(samples)

    # 3. Readiness
    readiness_resp = client.get(f"/readiness", params={"user_id": user_id})
    assert readiness_resp.status_code == 200
    readiness = readiness_resp.json()
    assert "readiness" in readiness
    assert readiness["readiness"] >= 0.0 and readiness["readiness"] <= 1.0
    assert readiness["hrv"] == 55.0
    assert readiness["resting_hr"] == 50.0

    # 4. First chat message (creates session implicitly)
    chat_msg1 = client.post("/chat/messages", json={"user_id": user_id, "message": "How is my recovery today?"})
    assert chat_msg1.status_code == 200, chat_msg1.text
    chat_data1 = chat_msg1.json()
    assert "session_id" in chat_data1
    session_id = chat_data1["session_id"]
    assert chat_data1["assistant_message"]["content"] != ""

    # 5. Follow-up chat message referencing existing session
    chat_msg2 = client.post("/chat/messages", json={"user_id": user_id, "message": "Give me a distance goal suggestion", "session_id": session_id})
    assert chat_msg2.status_code == 200, chat_msg2.text
    chat_data2 = chat_msg2.json()
    assert chat_data2["session_id"] == session_id
    assert chat_data2["assistant_message"]["content"].lower().find("goal") != -1

    # Cross-feature consistency: ensure goals endpoint returns created goals
    goals_list = client.get("/goals", params={"user_id": user_id})
    assert goals_list.status_code == 200
    goals_payload_returned = goals_list.json()
    assert len(goals_payload_returned) == 2
    returned_ids = {g["id"] for g in goals_payload_returned}
    assert set(created_goal_ids) == returned_ids

    # Chat context endpoint should include readiness segment
    ctx_resp = client.get(f"/chat/context/{user_id}")
    assert ctx_resp.status_code == 200
    ctx = ctx_resp.json()
    assert ctx["readiness"]["hrv"] == 55.0
    assert ctx["goals"]

    # Confirm messages listing works
    msgs_resp = client.get(f"/chat/messages/{session_id}")
    assert msgs_resp.status_code == 200
    msgs = msgs_resp.json()
    assert len(msgs) >= 4  # user+assistant for each of two messages

    # Dedup check: re-ingest identical samples should insert 0
    ingest_resp_dup = client.post("/health/samples", json={"samples": samples})
    assert ingest_resp_dup.status_code == 200
    dup_data = ingest_resp_dup.json()
    assert dup_data["inserted"] == 0

    # Cleanup: delete chat session
    del_resp = client.delete(f"/chat/sessions/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] == 1
