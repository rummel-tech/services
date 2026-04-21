"""Tests for Phase 2: Worker Agents and Signal Bus."""
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
# Signal bus unit tests
# ---------------------------------------------------------------------------

class TestSignalBus:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        import artemis.core.signals as sig
        self._orig_file = sig.SIGNALS_FILE
        sig.SIGNALS_FILE = Path(self._tmpdir) / "signals.json"

    def teardown_method(self):
        import artemis.core.signals as sig
        sig.SIGNALS_FILE = self._orig_file
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_publish_and_retrieve(self):
        from artemis.core.signals import publish, get_active_signals
        publish("body", "low_readiness", data={"score": 58})
        signals = get_active_signals()
        assert len(signals) == 1
        assert signals[0]["type"] == "low_readiness"
        assert signals[0]["source"] == "body"
        assert signals[0]["data"]["score"] == 58

    def test_publish_deduplicates_same_source_type(self):
        from artemis.core.signals import publish, get_active_signals
        publish("body", "low_readiness", data={"score": 60})
        publish("body", "low_readiness", data={"score": 55})
        signals = get_active_signals(signal_types=["low_readiness"])
        assert len(signals) == 1
        assert signals[0]["data"]["score"] == 55  # latest wins

    def test_filter_by_type(self):
        from artemis.core.signals import publish, get_active_signals
        publish("body", "low_readiness", data={"score": 58})
        publish("work", "deadline_approaching", data={"days": 2})
        readiness = get_active_signals(signal_types=["low_readiness"])
        assert len(readiness) == 1
        assert readiness[0]["type"] == "low_readiness"

    def test_clear_signal(self):
        from artemis.core.signals import publish, clear_signal, get_active_signals
        publish("body", "low_readiness")
        clear_signal("body", "low_readiness")
        signals = get_active_signals()
        assert len(signals) == 0

    def test_multiple_sources_same_type(self):
        from artemis.core.signals import publish, get_active_signals
        publish("body", "low_readiness", data={"score": 58})
        publish("work", "low_readiness", data={"score": 60})
        signals = get_active_signals(signal_types=["low_readiness"])
        assert len(signals) == 2

    def test_format_signals_for_prompt(self):
        from artemis.core.signals import publish, get_active_signals, format_signals_for_prompt
        publish("body", "low_readiness", data={"score": 58})
        signals = get_active_signals()
        formatted = format_signals_for_prompt(signals)
        assert "low_readiness" in formatted
        assert "body" in formatted

    def test_format_empty_signals(self):
        from artemis.core.signals import format_signals_for_prompt
        assert format_signals_for_prompt([]) == ""

    def test_zero_ttl_expires_immediately(self):
        from artemis.core.signals import publish, get_active_signals
        publish("body", "test_signal", ttl_hours=0)
        signals = get_active_signals()
        # ttl=0 means expires immediately — should not appear
        assert not any(s["type"] == "test_signal" for s in signals)


# ---------------------------------------------------------------------------
# Worker agent unit tests
# ---------------------------------------------------------------------------

class TestWorkerRegistry:
    def test_all_workers_registered(self):
        from artemis.core.workers import WORKER_REGISTRY
        expected = {"body", "mind", "work", "home", "travel"}
        assert set(WORKER_REGISTRY.keys()) == expected

    def test_body_agent_has_correct_modules(self):
        from artemis.core.workers import WORKER_REGISTRY
        body = WORKER_REGISTRY["body"]
        assert "workout-planner" in body.MODULE_IDS
        assert "meal-planner" in body.MODULE_IDS

    def test_mind_agent_has_correct_modules(self):
        from artemis.core.workers import WORKER_REGISTRY
        mind = WORKER_REGISTRY["mind"]
        assert "education-planner" in mind.MODULE_IDS
        assert "content-planner" in mind.MODULE_IDS

    def test_work_agent_has_correct_modules(self):
        from artemis.core.workers import WORKER_REGISTRY
        work = WORKER_REGISTRY["work"]
        assert "work-planner" in work.MODULE_IDS

    def test_home_agent_has_correct_modules(self):
        from artemis.core.workers import WORKER_REGISTRY
        home = WORKER_REGISTRY["home"]
        assert "home-manager" in home.MODULE_IDS
        assert "vehicle-manager" in home.MODULE_IDS

    def test_travel_agent_has_correct_modules(self):
        from artemis.core.workers import WORKER_REGISTRY
        travel = WORKER_REGISTRY["travel"]
        assert "trip-planner" in travel.MODULE_IDS

    def test_each_worker_has_domain_persona(self):
        from artemis.core.workers import WORKER_REGISTRY
        for agent_id, agent in WORKER_REGISTRY.items():
            assert len(agent.DOMAIN_PERSONA) > 100, f"{agent_id} persona is too short"

    def test_worker_builds_prompt_with_domain_expertise(self):
        from artemis.core.workers import WORKER_REGISTRY
        body = WORKER_REGISTRY["body"]
        prompt = body._build_prompt(
            user_name="Shawn",
            today="2026-04-21",
            modules="workout-planner, meal-planner",
            memory_context="## Vision\nBuild great things.",
            signal_block="",
            stoic_quote={"text": "Test.", "author": "Marcus Aurelius"},
        )
        assert "Body Agent" in prompt
        assert "performance coach" in prompt.lower() or "coach" in prompt.lower()
        assert "Shawn" in prompt

    def test_worker_prompt_includes_signals(self):
        from artemis.core.workers import WORKER_REGISTRY
        work = WORKER_REGISTRY["work"]
        prompt = work._build_prompt(
            user_name="Shawn",
            today="2026-04-21",
            modules="work-planner",
            memory_context="",
            signal_block="**Active cross-domain signals:**\n  • [body] low_readiness (score=58)",
        )
        assert "low_readiness" in prompt

    def test_workers_listen_to_relevant_signals(self):
        from artemis.core.workers import WORKER_REGISTRY
        # Work agent should listen to low_readiness from body
        work = WORKER_REGISTRY["work"]
        assert "low_readiness" in work.LISTENS_TO

        # Body agent should listen to deadline_approaching from work
        body = WORKER_REGISTRY["body"]
        assert "deadline_approaching" in body.LISTENS_TO

        # Mind agent should listen to deadline to pause new content
        mind = WORKER_REGISTRY["mind"]
        assert "deadline_approaching" in mind.LISTENS_TO


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


def test_list_workers_endpoint(client):
    r = client.get("/workers")
    assert r.status_code == 200
    data = r.json()
    assert "workers" in data
    assert len(data["workers"]) == 5
    ids = {w["id"] for w in data["workers"]}
    assert ids == {"body", "mind", "work", "home", "travel"}


def test_worker_not_found(client):
    r = client.post("/workers/nonexistent/chat", json={"message": "Hello"})
    assert r.status_code == 404


def test_publish_and_get_signals(client):
    r = client.post("/workers/signals", json={
        "source": "body",
        "signal_type": "low_readiness",
        "data": {"score": 58, "days": 3},
        "ttl_hours": 24,
    })
    assert r.status_code == 200
    assert r.json()["published"] is True

    r2 = client.get("/workers/signals")
    assert r2.status_code == 200
    signals = r2.json()["signals"]
    assert any(s["type"] == "low_readiness" for s in signals)


def test_delete_signal(client):
    client.post("/workers/signals", json={
        "source": "work",
        "signal_type": "deadline_approaching",
        "data": {"days": 1},
        "ttl_hours": 24,
    })
    r = client.delete("/workers/signals/deadline_approaching")
    assert r.status_code == 200

    r2 = client.get("/workers/signals?signal_type=deadline_approaching")
    assert len(r2.json()["signals"]) == 0


def test_workers_route_registered(client):
    """Verify the worker chat route is registered as a parameterized path."""
    routes = {r.path for r in client.app.routes if hasattr(r, "path")}
    # The route is /workers/{agent_id}/chat — a single parameterized route handles all agents
    assert "/workers/{agent_id}/chat" in routes
