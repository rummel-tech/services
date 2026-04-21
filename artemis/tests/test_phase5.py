"""Tests for Phase 5: Pattern learning, goal evolution, multi-modal, accountability."""
import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ENABLE_METRICS", "false")

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class _MemoryIsolation:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        import artemis.core.memory as mem
        import artemis.core.outcomes as oc
        import artemis.core.goal_evolution as ge
        self._orig_mem_dir = mem.MEMORY_DIR
        self._orig_outcomes_dir = oc.OUTCOMES_DIR
        self._orig_goal_file = ge.GOAL_HEALTH_FILE

        mem.MEMORY_DIR = Path(self._tmpdir)
        mem.VISION_FILE = Path(self._tmpdir) / "life_vision.md"
        mem.CONTEXT_FILE = Path(self._tmpdir) / "running_context.json"
        mem.SESSIONS_DIR = Path(self._tmpdir) / "sessions"
        mem.INSIGHTS_DIR = Path(self._tmpdir) / "insights"
        mem.STOIC_QUOTES_FILE = Path(self._tmpdir) / "insights" / "stoic_quotes.json"
        oc.OUTCOMES_DIR = Path(self._tmpdir) / "outcomes"
        ge.GOAL_HEALTH_FILE = Path(self._tmpdir) / "goal_health.json"

    def teardown_method(self):
        import artemis.core.memory as mem
        import artemis.core.outcomes as oc
        import artemis.core.goal_evolution as ge
        mem.MEMORY_DIR = self._orig_mem_dir
        oc.OUTCOMES_DIR = self._orig_outcomes_dir
        ge.GOAL_HEALTH_FILE = self._orig_goal_file
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Outcomes logging + correlations
# ---------------------------------------------------------------------------

class TestOutcomes(_MemoryIsolation):
    def test_log_and_load_outcome(self):
        from artemis.core.outcomes import log_daily_outcome, load_recent_outcomes
        entry = log_daily_outcome(
            day=date.today().isoformat(),
            inputs={"training_done": True, "sleep_hours": 8},
            outcomes={"readiness": 82},
        )
        assert entry["inputs"]["training_done"] is True
        assert entry["outcomes"]["readiness"] == 82
        loaded = load_recent_outcomes(n_days=7)
        assert len(loaded) == 1

    def test_update_existing_day(self):
        from artemis.core.outcomes import log_daily_outcome
        today = date.today().isoformat()
        log_daily_outcome(day=today, inputs={"training_done": True})
        entry = log_daily_outcome(day=today, outcomes={"mood": 4})
        assert entry["inputs"]["training_done"] is True
        assert entry["outcomes"]["mood"] == 4

    def test_snapshot_from_running_context(self):
        from artemis.core.memory import update_running_context
        from artemis.core.outcomes import snapshot_outcome_from_context
        update_running_context({
            "body": {"current_readiness": 75, "weekly_workouts_completed": 4},
            "work": {"deep_work_hours_this_week": 12, "deep_work_target_hours": 20,
                     "goal_completion_this_week": 3},
            "spirit": {"morning_practice_streak": 5, "evening_review_streak": 3},
        })
        entry = snapshot_outcome_from_context()
        assert entry["outcomes"]["readiness"] == 75
        assert entry["inputs"]["morning_practice_done"] is True

    def test_correlation_insufficient_data(self):
        from artemis.core.outcomes import analyze_patterns
        result = analyze_patterns(n_days=30, min_sample=5)
        assert result["insufficient_data"] is True

    def test_correlation_detects_input_effect(self):
        from artemis.core.outcomes import analyze_patterns, log_daily_outcome
        # 8 days with training → high readiness
        for i in range(8):
            d = (date.today() - timedelta(days=i)).isoformat()
            log_daily_outcome(
                day=d,
                inputs={"training_done": True, "morning_practice_done": True},
                outcomes={"readiness": 80 + (i % 3)},
            )
        # 8 days without training → lower readiness
        for i in range(8, 16):
            d = (date.today() - timedelta(days=i)).isoformat()
            log_daily_outcome(
                day=d,
                inputs={"training_done": False, "morning_practice_done": False},
                outcomes={"readiness": 60 + (i % 3)},
            )
        result = analyze_patterns(n_days=30, min_sample=5)
        assert result["insufficient_data"] is False
        correlations = result["correlations"]
        training_corr = next((c for c in correlations if c["input"] == "training_done"), None)
        assert training_corr is not None
        assert training_corr["delta"] > 0


# ---------------------------------------------------------------------------
# Goal evolution
# ---------------------------------------------------------------------------

class TestGoalEvolution(_MemoryIsolation):
    def test_register_goal(self):
        from artemis.core.goal_evolution import register_goal, get_goal_health
        register_goal("g1", "Launch Workout Planner commercially", domain="work")
        goals = get_goal_health()
        assert len(goals) == 1
        assert goals[0]["id"] == "g1"
        assert goals[0]["status"] == "active"

    def test_mark_progress(self):
        from artemis.core.goal_evolution import register_goal, mark_progress, get_goal_health
        register_goal("g1", "Test goal")
        mark_progress("g1")
        goals = get_goal_health()
        assert goals[0]["progress_events"] >= 1

    def test_retire_goal(self):
        from artemis.core.goal_evolution import register_goal, retire_goal, get_goal_health
        register_goal("g1", "To retire")
        retire_goal("g1", reason="No longer relevant")
        goals = get_goal_health()
        assert goals[0]["status"] == "retired"

    def test_retire_nonexistent_returns_false(self):
        from artemis.core.goal_evolution import retire_goal
        assert retire_goal("nonexistent") is False

    def test_dormant_detection(self):
        from artemis.core.goal_evolution import register_goal, get_dormant_goals, _load, _save
        register_goal("g1", "Old goal")
        old_date = (date.today() - timedelta(days=30)).isoformat()
        data = _load()
        data["g1"]["last_progress"] = old_date
        data["g1"]["last_mentioned"] = old_date
        _save(data)

        dormant = get_dormant_goals()
        assert len(dormant) == 1
        assert dormant[0]["id"] == "g1"

    def test_sync_from_running_context(self):
        from artemis.core.memory import update_running_context
        from artemis.core.goal_evolution import sync_from_running_context, get_goal_health
        update_running_context({
            "work": {
                "active_projects": ["Artemis Platform", "Workout Planner Commercial"],
                "top_priority": "Complete Phase 5",
            }
        })
        registered = sync_from_running_context()
        assert registered >= 2
        goals = get_goal_health()
        titles = [g["title"] for g in goals]
        assert any("Artemis" in t for t in titles)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from artemis.api.main import app
    from artemis.core.auth import validate_token

    async def _mock_token():
        return {"sub": "test-user", "name": "Shawn", "email": "shawn@test.com", "modules": []}

    app.dependency_overrides[validate_token] = _mock_token

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# Evolution endpoints

def test_outcomes_endpoint(client):
    r = client.get("/evolution/outcomes?days=7")
    assert r.status_code == 200
    assert "count" in r.json()


def test_outcomes_save(client):
    r = client.post("/evolution/outcomes", json={
        "inputs": {"training_done": True},
        "outcomes": {"readiness": 78},
    })
    assert r.status_code == 200
    assert r.json()["saved"] is True


def test_outcomes_snapshot(client):
    r = client.post("/evolution/outcomes/snapshot")
    assert r.status_code == 200
    assert r.json()["captured"] is True


def test_correlations_endpoint(client):
    r = client.get("/evolution/correlations")
    assert r.status_code == 200
    data = r.json()
    assert "correlations" in data
    assert "days_logged" in data


def test_goals_endpoint(client):
    r = client.get("/evolution/goals")
    assert r.status_code == 200
    assert "goals" in r.json()


def test_register_and_retire_goal(client):
    r = client.post("/evolution/goals", json={
        "id": "test_goal_1",
        "title": "Test goal for retirement",
        "domain": "work",
    })
    assert r.status_code == 200

    r2 = client.post(f"/evolution/goals/test_goal_1/retire", json={"reason": "Test complete"})
    assert r2.status_code == 200


def test_dormant_goals_endpoint(client):
    r = client.get("/evolution/goals/dormant")
    assert r.status_code == 200
    assert "dormant" in r.json()


def test_goals_scan_endpoint(client):
    r = client.post("/evolution/goals/scan")
    assert r.status_code == 200
    assert "registered_from_context" in r.json()


# Multimodal endpoints

def test_voice_briefing(client):
    r = client.get("/multimodal/briefing/voice")
    assert r.status_code == 200
    data = r.json()
    assert "spoken_text" in data
    assert "Good morning" in data["spoken_text"]
    assert "**" not in data["spoken_text"]  # no markdown


def test_widget_data(client):
    r = client.get("/multimodal/widget")
    assert r.status_code == 200
    data = r.json()
    assert "status_color" in data
    assert "readiness" in data
    assert "counts" in data
    assert "stoic_quote" in data


def test_weekly_digest(client):
    r = client.get("/multimodal/digest/weekly")
    assert r.status_code == 200
    data = r.json()
    assert "markdown" in data
    assert "week_start" in data
    assert "Artemis Digest" in data["markdown"]


def test_all_phase5_routes_registered(client):
    routes = {r.path for r in client.app.routes if hasattr(r, "path")}
    required = [
        "/evolution/outcomes",
        "/evolution/correlations",
        "/evolution/goals",
        "/evolution/goals/dormant",
        "/evolution/goals/scan",
        "/multimodal/briefing/voice",
        "/multimodal/widget",
        "/multimodal/digest/weekly",
        "/multimodal/voice-input",
    ]
    for path in required:
        assert path in routes, f"Missing route: {path}"
