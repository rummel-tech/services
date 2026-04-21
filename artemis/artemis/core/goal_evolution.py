"""Goal lifecycle tracking and dormancy detection.

Tracks each goal's health: when it was last mentioned, last scheduled,
last progress made. Surfaces goals that have gone silent so they can be
explicitly retired, revived, or evolved.

States:
  active    — mentioned or worked on in last 7 days
  stale     — 8-21 days since last activity
  dormant   — 22-45 days since last activity (candidate for review)
  retired   — user has chosen to archive
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from artemis.core.memory import MEMORY_DIR, load_recent_sessions, load_running_context

log = logging.getLogger("artemis.goals")

GOAL_HEALTH_FILE = MEMORY_DIR / "goal_health.json"


def _load() -> dict:
    if not GOAL_HEALTH_FILE.exists():
        return {}
    try:
        return json.loads(GOAL_HEALTH_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    GOAL_HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    GOAL_HEALTH_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_goal(goal_id: str, title: str, domain: str = "work") -> dict:
    """Register a new goal in the health tracker."""
    data = _load()
    today = date.today().isoformat()
    if goal_id not in data:
        data[goal_id] = {
            "id": goal_id,
            "title": title,
            "domain": domain,
            "status": "active",
            "created_at": today,
            "last_mentioned": today,
            "last_progress": today,
            "mention_count": 1,
            "progress_events": 0,
        }
    else:
        data[goal_id]["title"] = title
        data[goal_id]["last_mentioned"] = today
        data[goal_id]["mention_count"] = data[goal_id].get("mention_count", 0) + 1
    _save(data)
    return data[goal_id]


def mark_progress(goal_id: str) -> None:
    data = _load()
    if goal_id in data:
        data[goal_id]["last_progress"] = date.today().isoformat()
        data[goal_id]["progress_events"] = data[goal_id].get("progress_events", 0) + 1
        data[goal_id]["status"] = "active"
        _save(data)


def retire_goal(goal_id: str, reason: Optional[str] = None) -> bool:
    data = _load()
    if goal_id not in data:
        return False
    data[goal_id]["status"] = "retired"
    data[goal_id]["retired_at"] = date.today().isoformat()
    if reason:
        data[goal_id]["retirement_reason"] = reason
    _save(data)
    return True


def _days_since(iso_date: Optional[str]) -> Optional[int]:
    if not iso_date:
        return None
    try:
        d = date.fromisoformat(iso_date[:10])
        return (date.today() - d).days
    except (ValueError, TypeError):
        return None


def _compute_status(goal: dict) -> str:
    if goal.get("status") == "retired":
        return "retired"
    days = _days_since(goal.get("last_progress") or goal.get("last_mentioned"))
    if days is None:
        return "active"
    if days <= 7:
        return "active"
    if days <= 21:
        return "stale"
    return "dormant"


def get_goal_health() -> list[dict]:
    """Return all goals with current computed status."""
    data = _load()
    results = []
    for goal in data.values():
        g = dict(goal)
        g["status"] = _compute_status(g)
        g["days_since_progress"] = _days_since(g.get("last_progress"))
        g["days_since_mention"] = _days_since(g.get("last_mentioned"))
        results.append(g)
    results.sort(key=lambda g: g.get("days_since_progress") or 0, reverse=True)
    return results


def get_dormant_goals() -> list[dict]:
    """Return goals needing review (dormant status, not retired)."""
    return [g for g in get_goal_health() if g["status"] == "dormant"]


def scan_sessions_for_mentions(n_sessions: int = 14) -> int:
    """Scan recent sessions for goal title mentions. Updates mention counts."""
    data = _load()
    if not data:
        return 0

    sessions = load_recent_sessions(n=n_sessions)
    if not sessions:
        return 0

    updated = 0
    for session in sessions:
        content = session.get("content", "").lower()
        for goal_id, goal in data.items():
            if goal.get("status") == "retired":
                continue
            title_words = goal.get("title", "").lower().split()
            if len(title_words) < 2:
                continue
            # Match if multiple significant words from the title appear
            matches = sum(1 for w in title_words if len(w) > 4 and w in content)
            if matches >= 2:
                session_date = session.get("date")
                if session_date:
                    last = goal.get("last_mentioned", "")
                    if session_date > last:
                        goal["last_mentioned"] = session_date
                        goal["mention_count"] = goal.get("mention_count", 0) + 1
                        updated += 1
    _save(data)
    return updated


def sync_from_running_context() -> int:
    """Auto-register active projects from running context."""
    ctx = load_running_context()
    work = ctx.get("work", {}) or {}
    projects = work.get("active_projects", []) or []

    registered = 0
    for proj in projects:
        goal_id = f"project__{proj.replace(' ', '_').lower()}"
        data = _load()
        if goal_id not in data:
            register_goal(goal_id, proj, domain="work")
            registered += 1

    top = work.get("top_priority")
    if top:
        goal_id = f"priority__{str(top)[:40].replace(' ', '_').lower()}"
        data = _load()
        if goal_id not in data:
            register_goal(goal_id, str(top), domain="work")
            registered += 1

    return registered
