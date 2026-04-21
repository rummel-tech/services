"""Tests for Phase 3: Pattern Detection, Aggregation, and Weekly/Quarterly Synthesis."""
import json
import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ENABLE_METRICS", "false")

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ---------------------------------------------------------------------------
# Pattern detector unit tests
# ---------------------------------------------------------------------------

class TestPatternDetector:
    """Tests for artemis.core.patterns.detect_patterns."""

    def _ctx(self, **kwargs) -> dict:
        """Build a minimal context dict for testing."""
        base = {
            "body": {
                "current_readiness": 80,
                "weekly_workouts_completed": 4,
                "weekly_workouts_target": 5,
                "nutrition_on_track": True,
            },
            "mind": {
                "content_queue_depth": 5,
                "active_learning_goal": "Systems thinking",
            },
            "work": {
                "deep_work_hours_this_week": 18,
                "deep_work_target_hours": 20,
                "goal_completion_this_week": 3,
                "top_priority": "Ship Phase 3",
            },
            "spirit": {
                "morning_practice_streak": 5,
                "evening_review_streak": 4,
                "sabbath_observed_last_week": True,
            },
            "wealth": {"financial_pressure_level": "low", "monthly_recurring_revenue": 0},
            "travel": {"last_trip_date": None, "days_since_last_trip": None},
            "open_loops": ["Fix bug in auth"],
        }
        for k, v in kwargs.items():
            if isinstance(v, dict) and k in base:
                base[k].update(v)
            else:
                base[k] = v
        return base

    def test_no_patterns_on_healthy_context(self):
        from artemis.core.patterns import detect_patterns
        ctx = self._ctx()
        patterns = detect_patterns(context=ctx, signals=[])
        # Healthy context should produce no warnings or criticals
        assert not any(p.severity in ("warning", "critical") for p in patterns)

    def test_burnout_warning_fires_on_multiple_stress_signals(self):
        from artemis.core.patterns import detect_patterns
        ctx = self._ctx(
            body={"current_readiness": 55, "weekly_workouts_completed": 1, "weekly_workouts_target": 5},
            work={"deep_work_hours_this_week": 5, "deep_work_target_hours": 20, "goal_completion_this_week": 0},
            spirit={"morning_practice_streak": 0, "evening_review_streak": 0, "sabbath_observed_last_week": False},
            wealth={"financial_pressure_level": "high"},
        )
        signals = [{"type": "deadline_approaching", "source": "work", "data": {}}]
        patterns = detect_patterns(context=ctx, signals=signals)
        names = [p.name for p in patterns]
        assert "burnout_early_warning" in names

    def test_burnout_not_fired_on_partial_stress(self):
        from artemis.core.patterns import detect_patterns
        # Only one stress signal — not enough for burnout
        ctx = self._ctx(
            body={"current_readiness": 62, "weekly_workouts_completed": 3, "weekly_workouts_target": 5},
        )
        patterns = detect_patterns(context=ctx, signals=[])
        names = [p.name for p in patterns]
        assert "burnout_early_warning" not in names

    def test_peak_window_fires_on_high_readiness(self):
        from artemis.core.patterns import detect_patterns
        ctx = self._ctx(
            body={"current_readiness": 88, "weekly_workouts_completed": 5, "weekly_workouts_target": 5},
            work={"deep_work_hours_this_week": 18, "deep_work_target_hours": 20},
        )
        patterns = detect_patterns(context=ctx, signals=[])
        names = [p.name for p in patterns]
        assert "peak_performance_window" in names

    def test_peak_window_suppressed_by_deadline(self):
        from artemis.core.patterns import detect_patterns
        ctx = self._ctx(
            body={"current_readiness": 88},
            work={"deep_work_hours_this_week": 18, "deep_work_target_hours": 20},
        )
        signals = [{"type": "deadline_approaching", "source": "work", "data": {}}]
        patterns = detect_patterns(context=ctx, signals=signals)
        names = [p.name for p in patterns]
        # Peak window should NOT fire when deadline is looming
        assert "peak_performance_window" not in names

    def test_physical_neglect_fires_on_multiple_body_failures(self):
        from artemis.core.patterns import detect_patterns
        ctx = self._ctx(
            body={"current_readiness": 50, "weekly_workouts_completed": 1, "weekly_workouts_target": 5,
                  "nutrition_on_track": False},
        )
        signals = [{"type": "low_readiness", "source": "body", "data": {"score": 50}}]
        patterns = detect_patterns(context=ctx, signals=signals)
        names = [p.name for p in patterns]
        assert "physical_neglect" in names

    def test_learning_application_lag_fires_on_bloated_queue_and_no_work_output(self):
        from artemis.core.patterns import detect_patterns
        ctx = self._ctx(
            mind={"content_queue_depth": 18, "active_learning_goal": "Many things"},
            work={"goal_completion_this_week": 0, "deep_work_hours_this_week": 2, "deep_work_target_hours": 20},
        )
        patterns = detect_patterns(context=ctx, signals=[])
        names = [p.name for p in patterns]
        assert "learning_application_lag" in names

    def test_drift_from_values_fires_on_lapsed_practices(self):
        from artemis.core.patterns import detect_patterns
        ctx = self._ctx(
            spirit={"morning_practice_streak": 0, "evening_review_streak": 0,
                    "sabbath_observed_last_week": False, "last_evening_review": "2026-03-01"},
            work={"goal_completion_this_week": 0},
        )
        patterns = detect_patterns(context=ctx, signals=[])
        names = [p.name for p in patterns]
        assert "drift_from_values" in names

    def test_financial_anxiety_fires_on_pressure(self):
        from artemis.core.patterns import detect_patterns
        ctx = self._ctx(wealth={"financial_pressure_level": "high", "monthly_recurring_revenue": 0})
        patterns = detect_patterns(context=ctx, signals=[])
        names = [p.name for p in patterns]
        assert "financial_anxiety" in names

    def test_open_loop_overload_fires_at_threshold(self):
        from artemis.core.patterns import detect_patterns
        ctx = self._ctx()
        ctx["open_loops"] = [f"Loop {i}" for i in range(8)]
        patterns = detect_patterns(context=ctx, signals=[])
        names = [p.name for p in patterns]
        assert "open_loop_accumulation" in names

    def test_critical_suppresses_same_domain_lower_severity(self):
        from artemis.core.patterns import detect_patterns
        # Burnout (critical, body+work+spirit domain) should suppress physical_neglect (warning, body)
        ctx = self._ctx(
            body={"current_readiness": 50, "weekly_workouts_completed": 0, "weekly_workouts_target": 5,
                  "nutrition_on_track": False},
            work={"deep_work_hours_this_week": 3, "deep_work_target_hours": 20, "goal_completion_this_week": 0},
            spirit={"morning_practice_streak": 0, "evening_review_streak": 0, "sabbath_observed_last_week": False},
            wealth={"financial_pressure_level": "high"},
        )
        signals = [
            {"type": "deadline_approaching", "source": "work", "data": {}},
            {"type": "low_readiness", "source": "body", "data": {"score": 50}},
        ]
        patterns = detect_patterns(context=ctx, signals=signals)
        names = [p.name for p in patterns]
        # If burnout is critical, physical_neglect (same domain) should be suppressed
        if "burnout_early_warning" in names:
            burnout = next(p for p in patterns if p.name == "burnout_early_warning")
            if burnout.severity == "critical":
                assert "physical_neglect" not in names

    def test_patterns_sorted_critical_first(self):
        from artemis.core.patterns import detect_patterns
        ctx = self._ctx(
            body={"current_readiness": 50, "weekly_workouts_completed": 0, "weekly_workouts_target": 5},
            work={"deep_work_hours_this_week": 3, "deep_work_target_hours": 20, "goal_completion_this_week": 0},
            spirit={"morning_practice_streak": 0, "evening_review_streak": 0},
            wealth={"financial_pressure_level": "high"},
        )
        ctx["open_loops"] = [f"Loop {i}" for i in range(8)]
        patterns = detect_patterns(context=ctx, signals=[])

        order = {"critical": 0, "warning": 1, "insight": 2}
        if len(patterns) > 1:
            for i in range(len(patterns) - 1):
                assert order[patterns[i].severity] <= order[patterns[i + 1].severity]

    def test_format_patterns_for_briefing(self):
        from artemis.core.patterns import detect_patterns, format_patterns_for_briefing
        ctx = self._ctx(wealth={"financial_pressure_level": "high"})
        patterns = detect_patterns(context=ctx, signals=[])
        formatted = format_patterns_for_briefing(patterns)
        if patterns:
            assert "PATTERNS" in formatted
            assert len(formatted) > 50

    def test_format_empty_patterns(self):
        from artemis.core.patterns import format_patterns_for_briefing
        assert format_patterns_for_briefing([]) == ""


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


def test_patterns_endpoint_returns_structure(client):
    r = client.get("/synthesis/patterns")
    assert r.status_code == 200
    data = r.json()
    assert "patterns" in data
    assert "count" in data
    assert "has_critical" in data
    assert "has_warning" in data
    assert isinstance(data["patterns"], list)


def test_weekly_review_endpoint(client):
    r = client.get("/synthesis/weekly")
    assert r.status_code == 200
    data = r.json()
    assert "week" in data
    assert "scorecards" in data
    assert "prompts" in data
    assert "wins" in data["prompts"]
    assert "body" in data["scorecards"]
    assert "work" in data["scorecards"]


def test_save_weekly_review(client):
    r = client.post("/synthesis/weekly", json={
        "wins": "Completed Phases 1, 2, and 3 of Artemis agent system",
        "misses": "Didn't get to the evening review every day",
        "work_reflection": "Deep work was consistent. Artemis is taking shape.",
        "spirit_reflection": "Morning practice held. Evening slipped mid-week.",
        "next_week_focus": "First real conversation with Artemis — complete intake session",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["saved"] is True


def test_quarterly_review_endpoint(client):
    r = client.get("/synthesis/quarterly")
    assert r.status_code == 200
    data = r.json()
    assert "quarter" in data
    assert "prompts" in data
    assert "biggest_win" in data["prompts"]
    assert "next_quarter_focus" in data["prompts"]
    assert "vision_document" in data


def test_save_quarterly_update(client):
    r = client.post("/synthesis/quarterly/update", json={
        "biggest_win": "Built the Artemis agent system — Phases 1, 2, and 3 complete",
        "next_quarter_focus": "Launch Workout Planner commercially and complete Artemis intake",
        "domain_updates": {"work": {"top_priority": "Artemis intake + Workout Planner launch"}},
    })
    assert r.status_code == 200
    assert r.json()["saved"] is True


def test_snapshot_endpoint_returns_domains(client):
    r = client.get("/synthesis/snapshot")
    assert r.status_code == 200
    data = r.json()
    assert "domains" in data
    assert "patterns" in data
    assert "date" in data


def test_morning_briefing_includes_patterns(client):
    r = client.get("/briefing/morning")
    assert r.status_code == 200
    data = r.json()
    assert "patterns" in data
    assert "has_critical" in data
    assert isinstance(data["patterns"], list)


def test_all_synthesis_routes_registered(client):
    routes = {r.path for r in client.app.routes if hasattr(r, "path")}
    assert "/synthesis/patterns" in routes
    assert "/synthesis/weekly" in routes
    assert "/synthesis/quarterly" in routes
    assert "/synthesis/snapshot" in routes
