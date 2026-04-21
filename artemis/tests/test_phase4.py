"""Tests for Phase 4: Background monitoring, notifications, proposals, external agents."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ENABLE_METRICS", "false")

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ---------------------------------------------------------------------------
# Monitor unit tests
# ---------------------------------------------------------------------------

class TestMonitorCore:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        import artemis.core.monitor as mon
        import artemis.core.memory as mem
        self._orig_mem_dir = mem.MEMORY_DIR
        mem.MEMORY_DIR = Path(self._tmpdir)
        mem.VISION_FILE = Path(self._tmpdir) / "life_vision.md"
        mem.CONTEXT_FILE = Path(self._tmpdir) / "running_context.json"
        mem.SESSIONS_DIR = Path(self._tmpdir) / "sessions"
        mem.INSIGHTS_DIR = Path(self._tmpdir) / "insights"
        mem.STOIC_QUOTES_FILE = Path(self._tmpdir) / "insights" / "stoic_quotes.json"
        mon.NOTIFICATIONS_FILE = Path(self._tmpdir) / "notifications.json"
        mon.PROPOSALS_FILE = Path(self._tmpdir) / "proposals.json"
        mon.MONITOR_LOG_FILE = Path(self._tmpdir) / "monitor_log.json"
        mon.BRIEFINGS_DIR = Path(self._tmpdir) / "briefings"

    def teardown_method(self):
        import artemis.core.memory as mem
        mem.MEMORY_DIR = self._orig_mem_dir
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_push_and_get_notifications(self):
        from artemis.core.monitor import push_notification, get_unread_notifications
        push_notification("Test Alert", "Something needs attention.", severity="warning")
        unread = get_unread_notifications()
        assert len(unread) == 1
        assert unread[0]["title"] == "Test Alert"
        assert unread[0]["severity"] == "warning"
        assert not unread[0]["read"]

    def test_mark_notifications_read(self):
        from artemis.core.monitor import push_notification, mark_notifications_read, get_unread_notifications
        push_notification("Notif 1", "Body 1")
        push_notification("Notif 2", "Body 2")
        count = mark_notifications_read()
        assert count == 2
        assert len(get_unread_notifications()) == 0

    def test_add_and_get_proposals(self):
        from artemis.core.monitor import add_proposal, get_pending_proposals
        proposal = add_proposal(
            proposal_type="deep_work_block",
            title="Protect morning focus block",
            description="Deep work is at 40% of target.",
            domain="work",
        )
        assert proposal["status"] == "pending"
        pending = get_pending_proposals()
        assert len(pending) == 1
        assert pending[0]["type"] == "deep_work_block"

    def test_proposal_deduplication(self):
        from artemis.core.monitor import add_proposal, get_pending_proposals
        add_proposal("deep_work_block", "First proposal", "Desc 1")
        add_proposal("deep_work_block", "Updated proposal", "Desc 2")
        pending = get_pending_proposals()
        # Should only have one — second replaces first
        assert len(pending) == 1
        assert pending[0]["title"] == "Updated proposal"

    def test_update_proposal_status(self):
        from artemis.core.monitor import add_proposal, update_proposal_status, get_pending_proposals
        prop = add_proposal("recovery_day", "Recovery", "Take it easy")
        update_proposal_status(prop["id"], "accepted")
        pending = get_pending_proposals()
        assert len(pending) == 0

    def test_monitoring_cycle_runs_without_error(self):
        from artemis.core.memory import update_running_context
        from artemis.core.monitor import run_monitoring_cycle
        # Seed minimal context
        update_running_context({
            "body": {"current_readiness": 70, "weekly_workouts_completed": 3, "weekly_workouts_target": 5},
            "work": {"deep_work_hours_this_week": 15, "deep_work_target_hours": 20, "goal_completion_this_week": 2},
            "spirit": {"morning_practice_streak": 3, "evening_review_streak": 2},
            "wealth": {"financial_pressure_level": "low"},
            "open_loops": ["Fix auth bug", "Deploy to staging"],
        })
        summary = run_monitoring_cycle()
        assert "patterns_detected" in summary
        assert "actions" in summary
        assert isinstance(summary["actions"], list)

    def test_monitoring_cycle_creates_proposals_on_low_deep_work(self):
        from artemis.core.memory import update_running_context
        from artemis.core.monitor import run_monitoring_cycle, get_pending_proposals
        update_running_context({
            "work": {
                "deep_work_hours_this_week": 3,
                "deep_work_target_hours": 20,
                "goal_completion_this_week": 1,
            }
        })
        run_monitoring_cycle()
        proposals = get_pending_proposals()
        types = [p["type"] for p in proposals]
        assert "deep_work_block" in types

    def test_monitoring_cycle_logs_run(self):
        from artemis.core.monitor import run_monitoring_cycle, get_monitor_history
        run_monitoring_cycle()
        history = get_monitor_history(n=5)
        assert len(history) >= 1
        assert "patterns_detected" in history[-1]
        assert "timestamp" in history[-1]

    def test_monitoring_cycle_pushes_notification_on_lapsed_spirit(self):
        from artemis.core.memory import update_running_context
        from artemis.core.monitor import run_monitoring_cycle, get_unread_notifications
        from artemis.core.monitor import mark_notifications_read
        mark_notifications_read()  # clear existing
        update_running_context({
            "spirit": {"morning_practice_streak": 0, "evening_review_streak": 0}
        })
        run_monitoring_cycle()
        notifs = get_unread_notifications()
        spirit_notifs = [n for n in notifs if n.get("domain") == "spirit"]
        assert len(spirit_notifs) >= 1


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


def test_monitor_status_endpoint(client):
    r = client.get("/monitor/status")
    assert r.status_code == 200
    data = r.json()
    assert "unread_notifications" in data
    assert "pending_proposals" in data
    assert "modules_healthy" in data


def test_monitor_run_endpoint(client):
    r = client.post("/monitor/run")
    assert r.status_code == 200
    data = r.json()
    assert data["triggered"] is True
    assert "summary" in data
    assert "patterns_detected" in data["summary"]


def test_monitor_history_endpoint(client):
    client.post("/monitor/run")
    r = client.get("/monitor/history?n=5")
    assert r.status_code == 200
    assert "runs" in r.json()


def test_notifications_endpoint(client):
    r = client.get("/monitor/notifications")
    assert r.status_code == 200
    data = r.json()
    assert "notifications" in data
    assert "count" in data


def test_mark_notifications_read(client):
    r = client.post("/monitor/notifications/read")
    assert r.status_code == 200
    assert "marked_read" in r.json()


def test_proposals_endpoint(client):
    r = client.get("/monitor/proposals")
    assert r.status_code == 200
    data = r.json()
    assert "proposals" in data
    assert "count" in data


def test_reject_nonexistent_proposal(client):
    r = client.post("/monitor/proposals/fake-id-123/reject")
    assert r.status_code == 404


def test_research_endpoint_no_api_key(client):
    """Without ANTHROPIC_API_KEY set, research returns graceful error."""
    r = client.post("/research/query", json={"query": "What is stoicism?", "use_web": False})
    assert r.status_code == 200
    data = r.json()
    assert "answer" in data
    # No key → graceful error message
    assert len(data["answer"]) > 0


def test_summarize_endpoint_no_api_key(client):
    """Without ANTHROPIC_API_KEY, summarize returns graceful error."""
    r = client.post("/research/summarize", json={
        "text": "Marcus Aurelius wrote Meditations as a personal journal.",
        "source_name": "Test text",
    })
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data


def test_improve_endpoint_empty_input(client):
    r = client.post("/research/improve", json={
        "failed_tool_calls": [],
        "missing_capabilities": [],
    })
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_all_phase4_routes_registered(client):
    routes = {r.path for r in client.app.routes if hasattr(r, "path")}
    for path in [
        "/monitor/status",
        "/monitor/run",
        "/monitor/history",
        "/monitor/notifications",
        "/monitor/proposals",
        "/research/query",
        "/research/summarize",
        "/research/improve",
    ]:
        assert path in routes, f"Route {path} not registered"
