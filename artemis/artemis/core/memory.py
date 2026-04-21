"""Artemis Memory Manager.

Manages four layers of persistent memory:
  1. Life Vision Document  (months/years)  — life_vision.md
  2. Running Context       (weeks/months)  — running_context.json
  3. Session Logs          (days)          — sessions/YYYY-MM-DD.md
  4. Insights              (permanent)     — insights/*.md

All memory lives under MEMORY_DIR, which defaults to the `memory/` directory
relative to wherever the Artemis service is running from.
"""
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("artemis.memory")

# Resolve memory directory relative to this file's package root
_PACKAGE_ROOT = Path(__file__).parent.parent.parent  # services/artemis/
MEMORY_DIR = _PACKAGE_ROOT / "memory"

VISION_FILE = MEMORY_DIR / "life_vision.md"
CONTEXT_FILE = MEMORY_DIR / "running_context.json"
SESSIONS_DIR = MEMORY_DIR / "sessions"
INSIGHTS_DIR = MEMORY_DIR / "insights"
STOIC_QUOTES_FILE = INSIGHTS_DIR / "stoic_quotes.json"


def _ensure_dirs() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Life Vision
# ---------------------------------------------------------------------------

def load_life_vision() -> str:
    """Return the Life Vision Document as a markdown string."""
    _ensure_dirs()
    if VISION_FILE.exists():
        return VISION_FILE.read_text(encoding="utf-8")
    return "Life Vision Document not yet created. Guide the user through a vision intake session."


def save_life_vision(content: str) -> None:
    """Overwrite the Life Vision Document."""
    _ensure_dirs()
    VISION_FILE.write_text(content, encoding="utf-8")
    log.info("life_vision.md updated")


def vision_needs_intake() -> bool:
    """True if the vision document still has [COMPLETE] placeholders."""
    vision = load_life_vision()
    return "[Complete with Artemis" in vision or "*[Complete" in vision


# ---------------------------------------------------------------------------
# Running Context
# ---------------------------------------------------------------------------

def load_running_context() -> dict:
    """Load the current running context JSON."""
    _ensure_dirs()
    if CONTEXT_FILE.exists():
        try:
            return json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("running_context.json is malformed — returning empty context")
    return {}


def update_running_context(updates: dict) -> None:
    """Deep-merge updates into the running context and save."""
    ctx = load_running_context()

    def _merge(base: dict, delta: dict) -> dict:
        for k, v in delta.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k] = _merge(base[k], v)
            else:
                base[k] = v
        return base

    ctx = _merge(ctx, updates)
    ctx.setdefault("_meta", {})["last_updated"] = datetime.now(timezone.utc).date().isoformat()
    CONTEXT_FILE.write_text(json.dumps(ctx, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("running_context.json updated: %s", list(updates.keys()))


def add_open_loop(item: str) -> None:
    ctx = load_running_context()
    loops = ctx.get("open_loops", [])
    if item not in loops:
        loops.append(item)
    update_running_context({"open_loops": loops})


def close_open_loop(item: str) -> None:
    ctx = load_running_context()
    loops = [l for l in ctx.get("open_loops", []) if l != item]
    update_running_context({"open_loops": loops})


# ---------------------------------------------------------------------------
# Session logs
# ---------------------------------------------------------------------------

def save_session(summary: str, date: Optional[str] = None) -> Path:
    """Save a session summary. Returns the path written."""
    _ensure_dirs()
    day = date or datetime.now(timezone.utc).date().isoformat()
    path = SESSIONS_DIR / f"{day}.md"

    # Append if the file already exists (multiple sessions per day)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    timestamp = datetime.now(timezone.utc).strftime("%H:%M UTC")
    separator = f"\n\n---\n*Session ended {timestamp}*\n\n"
    path.write_text(existing + separator + summary, encoding="utf-8")
    log.info("session saved: %s", path.name)
    return path


def load_recent_sessions(n: int = 3) -> list[dict]:
    """Return the n most recent session summaries."""
    _ensure_dirs()
    files = sorted(SESSIONS_DIR.glob("*.md"), reverse=True)[:n]
    sessions = []
    for f in files:
        sessions.append({
            "date": f.stem,
            "content": f.read_text(encoding="utf-8")[:2000],  # cap at 2k chars
        })
    return sessions


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

def get_todays_stoic_quote() -> dict:
    """Return a deterministic daily Stoic quote (same quote all day)."""
    if not STOIC_QUOTES_FILE.exists():
        return {"text": "The impediment to action advances action. What stands in the way becomes the way.", "author": "Marcus Aurelius"}
    try:
        quotes = json.loads(STOIC_QUOTES_FILE.read_text(encoding="utf-8"))
        # Deterministic by day-of-year so it's stable within a day
        idx = datetime.now(timezone.utc).timetuple().tm_yday % len(quotes)
        return quotes[idx]
    except Exception:
        return {"text": "You have power over your mind, not outside events.", "author": "Marcus Aurelius"}


def save_insight(text: str, category: str = "general") -> None:
    """Append a captured insight to the insights log."""
    _ensure_dirs()
    insights_file = INSIGHTS_DIR / f"{category}.md"
    day = datetime.now(timezone.utc).date().isoformat()
    entry = f"\n## {day}\n{text}\n"
    existing = insights_file.read_text(encoding="utf-8") if insights_file.exists() else f"# {category.title()} Insights\n"
    insights_file.write_text(existing + entry, encoding="utf-8")


# ---------------------------------------------------------------------------
# Context assembly for prompt injection
# ---------------------------------------------------------------------------

def get_context_for_prompt(max_chars: int = 3000) -> str:
    """Assemble all memory layers into a compact string for the system prompt."""
    parts: list[str] = []

    # Life Vision (first 1500 chars — enough for current goals and rules)
    vision = load_life_vision()
    vision_preview = vision[:1500] + ("..." if len(vision) > 1500 else "")
    parts.append(f"## Life Vision (summary)\n{vision_preview}")

    # Running context (structured)
    ctx = load_running_context()
    ctx_lines = []
    for domain in ("body", "mind", "work", "spirit", "wealth"):
        d = ctx.get(domain, {})
        if d:
            notes = d.get("notes", "")
            ctx_lines.append(f"**{domain.title()}:** {notes}")

    open_loops = ctx.get("open_loops", [])
    if open_loops:
        ctx_lines.append(f"**Open loops:** {'; '.join(open_loops[:5])}")

    if ctx_lines:
        parts.append("## Current State\n" + "\n".join(ctx_lines))

    # Recent sessions (last 2, very compressed)
    sessions = load_recent_sessions(n=2)
    if sessions:
        session_summary = []
        for s in sessions:
            preview = s["content"][:400].replace("\n", " ")
            session_summary.append(f"**{s['date']}:** {preview}")
        parts.append("## Recent Sessions\n" + "\n".join(session_summary))

    full = "\n\n".join(parts)
    return full[:max_chars]
