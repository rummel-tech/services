"""Tests for Phase 1: Persona, Memory, and Briefing."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ENABLE_METRICS", "false")

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ---------------------------------------------------------------------------
# Memory manager unit tests (no HTTP)
# ---------------------------------------------------------------------------

class TestMemoryManager:
    """Tests for artemis.core.memory functions."""

    def setup_method(self):
        """Override MEMORY_DIR to a temp directory for each test."""
        self._tmpdir = tempfile.mkdtemp()
        import artemis.core.memory as mem
        self._orig_memory_dir = mem.MEMORY_DIR
        self._orig_vision = mem.VISION_FILE
        self._orig_context = mem.CONTEXT_FILE
        self._orig_sessions = mem.SESSIONS_DIR
        self._orig_insights = mem.INSIGHTS_DIR
        self._orig_stoic = mem.STOIC_QUOTES_FILE
        mem.MEMORY_DIR = Path(self._tmpdir)
        mem.VISION_FILE = Path(self._tmpdir) / "life_vision.md"
        mem.CONTEXT_FILE = Path(self._tmpdir) / "running_context.json"
        mem.SESSIONS_DIR = Path(self._tmpdir) / "sessions"
        mem.INSIGHTS_DIR = Path(self._tmpdir) / "insights"
        mem.STOIC_QUOTES_FILE = Path(self._tmpdir) / "insights" / "stoic_quotes.json"

    def teardown_method(self):
        import artemis.core.memory as mem
        mem.MEMORY_DIR = self._orig_memory_dir
        mem.VISION_FILE = self._orig_vision
        mem.CONTEXT_FILE = self._orig_context
        mem.SESSIONS_DIR = self._orig_sessions
        mem.INSIGHTS_DIR = self._orig_insights
        mem.STOIC_QUOTES_FILE = self._orig_stoic
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_load_vision_returns_default_when_missing(self):
        from artemis.core.memory import load_life_vision
        result = load_life_vision()
        assert "vision intake" in result.lower() or "not yet" in result.lower()

    def test_save_and_load_vision(self):
        from artemis.core.memory import save_life_vision, load_life_vision
        content = "# My Vision\nI will build something great."
        save_life_vision(content)
        loaded = load_life_vision()
        assert loaded == content

    def test_vision_needs_intake_when_placeholders_exist(self):
        from artemis.core.memory import save_life_vision, vision_needs_intake
        save_life_vision("# Vision\n*[Complete with Artemis in first intake session]*")
        assert vision_needs_intake() is True

    def test_vision_does_not_need_intake_when_complete(self):
        from artemis.core.memory import save_life_vision, vision_needs_intake
        save_life_vision("# Vision\nI am a builder of software and systems.")
        assert vision_needs_intake() is False

    def test_load_running_context_returns_empty_dict_when_missing(self):
        from artemis.core.memory import load_running_context
        ctx = load_running_context()
        assert isinstance(ctx, dict)

    def test_update_running_context_deep_merges(self):
        from artemis.core.memory import update_running_context, load_running_context
        update_running_context({"body": {"readiness": 85, "notes": "Good week"}})
        update_running_context({"body": {"readiness": 90}})
        ctx = load_running_context()
        # Deep merge: notes should survive the second update
        assert ctx["body"]["readiness"] == 90
        assert ctx["body"]["notes"] == "Good week"

    def test_save_and_load_session(self):
        from artemis.core.memory import save_session, load_recent_sessions
        save_session("## Discussion\nWe talked about the life vision.", date="2026-04-20")
        sessions = load_recent_sessions(n=5)
        assert len(sessions) == 1
        assert "Discussion" in sessions[0]["content"]
        assert sessions[0]["date"] == "2026-04-20"

    def test_save_insight_creates_file(self):
        from artemis.core.memory import save_insight, INSIGHTS_DIR
        save_insight("Deep work requires protecting morning hours.", category="patterns")
        insights_file = INSIGHTS_DIR / "patterns.md"
        assert insights_file.exists()
        assert "Deep work" in insights_file.read_text()

    def test_add_and_close_open_loop(self):
        from artemis.core.memory import add_open_loop, close_open_loop, load_running_context
        add_open_loop("Deploy Artemis to production")
        ctx = load_running_context()
        assert "Deploy Artemis to production" in ctx["open_loops"]
        close_open_loop("Deploy Artemis to production")
        ctx2 = load_running_context()
        assert "Deploy Artemis to production" not in ctx2["open_loops"]

    def test_stoic_quote_returns_fallback_when_no_file(self):
        from artemis.core.memory import get_todays_stoic_quote
        q = get_todays_stoic_quote()
        assert "text" in q
        assert "author" in q
        assert len(q["text"]) > 10

    def test_stoic_quote_from_file(self):
        from artemis.core.memory import get_todays_stoic_quote, INSIGHTS_DIR
        INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)
        quotes = [
            {"text": "Test quote one.", "author": "Author A"},
            {"text": "Test quote two.", "author": "Author B"},
        ]
        (INSIGHTS_DIR / "stoic_quotes.json").write_text(json.dumps(quotes))
        q = get_todays_stoic_quote()
        assert q["text"] in ("Test quote one.", "Test quote two.")

    def test_get_context_for_prompt_assembles_string(self):
        from artemis.core.memory import save_life_vision, update_running_context, get_context_for_prompt
        save_life_vision("# Vision\nI build software that matters.")
        update_running_context({"work": {"notes": "Working on Artemis platform."}})
        ctx = get_context_for_prompt()
        assert isinstance(ctx, str)
        assert len(ctx) > 50


# ---------------------------------------------------------------------------
# Persona unit tests
# ---------------------------------------------------------------------------

class TestPersona:
    def test_build_system_prompt_contains_persona(self):
        from artemis.core.persona import build_system_prompt
        prompt = build_system_prompt(
            token_payload={"name": "Shawn", "modules": ["workout-planner"]},
            memory_context="## Vision\nBuild great software.",
        )
        assert "Einstein" in prompt
        assert "Franklin" in prompt
        assert "Stoic" in prompt
        assert "Shawn" in prompt

    def test_build_system_prompt_includes_stoic_quote(self):
        from artemis.core.persona import build_system_prompt
        prompt = build_system_prompt(
            token_payload={"name": "Shawn", "modules": []},
            memory_context="",
            stoic_quote={"text": "Test wisdom.", "author": "Epictetus"},
        )
        assert "Test wisdom." in prompt
        assert "Epictetus" in prompt

    def test_build_system_prompt_includes_intake_addendum_when_needed(self):
        from artemis.core.persona import build_system_prompt
        prompt = build_system_prompt(
            token_payload={"name": "Shawn", "modules": []},
            memory_context="",
            needs_intake=True,
        )
        assert "First Session" in prompt or "intake" in prompt.lower()

    def test_build_system_prompt_no_intake_addendum_when_complete(self):
        from artemis.core.persona import build_system_prompt, INTAKE_ADDENDUM
        prompt = build_system_prompt(
            token_payload={"name": "Shawn", "modules": []},
            memory_context="",
            needs_intake=False,
        )
        assert INTAKE_ADDENDUM not in prompt


# ---------------------------------------------------------------------------
# API endpoint tests (requires test client)
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


def test_memory_vision_endpoint(client):
    r = client.get("/memory/vision")
    assert r.status_code == 200
    assert "content" in r.json()


def test_memory_context_endpoint(client):
    r = client.get("/memory/context")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_memory_sessions_endpoint(client):
    r = client.get("/memory/sessions")
    assert r.status_code == 200
    assert "sessions" in r.json()


def test_briefing_morning_endpoint(client):
    r = client.get("/briefing/morning")
    assert r.status_code == 200
    data = r.json()
    assert "briefing" in data
    assert "stoic_quote" in data
    assert "Good morning" in data["briefing"]


def test_briefing_evening_prompt_endpoint(client):
    r = client.get("/briefing/evening")
    assert r.status_code == 200
    data = r.json()
    assert "prompt" in data
    assert "fields" in data


def test_briefing_evening_save(client):
    r = client.post("/briefing/evening", json={
        "wins": "Completed the agent architecture",
        "stoic_reflection": "I could have been more patient",
        "gratitude": "Good health and meaningful work",
        "tomorrow_priority": "Start Phase 2 worker agents",
    })
    assert r.status_code == 200
    assert r.json()["saved"] is True


def test_memory_put_context(client):
    r = client.put("/memory/context", json={"updates": {"work": {"top_priority": "Ship Phase 1"}}})
    assert r.status_code == 200
    ctx = client.get("/memory/context").json()
    assert ctx.get("work", {}).get("top_priority") == "Ship Phase 1"
