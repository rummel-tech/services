"""Cross-agent signal bus.

Worker agents publish state changes that other agents and the orchestrator
can read. Signals are lightweight — just a type, a source, and a JSON payload.
They expire after 7 days and are consumed on read.

Storage: JSON file in memory/signals.json (no external dependencies).

Signal types:
    low_readiness          — Body → all (readiness score dropped below threshold)
    high_training_load     — Body → Mind/Work (heavy training week, protect recovery)
    nutrition_off_track    — Body → all (missing protein/calorie targets)
    skill_milestone        — Mind → Work (new skill acquired, unlock goals)
    learning_overload      — Mind → all (content queue bloated, simplify)
    deadline_approaching   — Work → all (big deadline, defer non-essentials)
    deep_work_protected    — Work → Body/Mind (guard morning block)
    goal_achieved          — Work → all (major milestone, celebrate + reset)
    financial_pressure     — Work/Wealth → all (revenue concern)
    trip_upcoming          — Travel → all (prepare cross-domain routine shift)
    environment_friction   — Home → all (home issue degrading performance)
    maintenance_overdue    — Home → Work (schedule maintenance block)
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("artemis.signals")

_PACKAGE_ROOT = Path(__file__).parent.parent.parent
SIGNALS_FILE = _PACKAGE_ROOT / "memory" / "signals.json"
SIGNAL_TTL_DAYS = 7


def _load() -> list[dict]:
    if not SIGNALS_FILE.exists():
        return []
    try:
        return json.loads(SIGNALS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(signals: list[dict]) -> None:
    SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SIGNALS_FILE.write_text(json.dumps(signals, indent=2, ensure_ascii=False), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_expired(signal: dict) -> bool:
    created = signal.get("created_at", "")
    try:
        dt = datetime.fromisoformat(created)
        return datetime.now(timezone.utc) - dt > timedelta(days=SIGNAL_TTL_DAYS)
    except Exception:
        return True


def publish(
    source: str,
    signal_type: str,
    data: Optional[dict] = None,
    ttl_hours: int = 24,
) -> None:
    """Publish a signal from a worker agent."""
    signals = [s for s in _load() if not _is_expired(s)]

    # Deduplicate: remove existing signal of same type from same source
    signals = [s for s in signals if not (s["source"] == source and s["type"] == signal_type)]

    signals.append({
        "source": source,
        "type": signal_type,
        "data": data or {},
        "created_at": _now_iso(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat(),
    })

    _save(signals)
    log.info("signal published: %s → %s", source, signal_type)


def get_active_signals(signal_types: Optional[list[str]] = None) -> list[dict]:
    """Return all non-expired signals, optionally filtered by type."""
    now = datetime.now(timezone.utc)
    signals = []
    for s in _load():
        if _is_expired(s):
            continue
        try:
            expires = datetime.fromisoformat(s["expires_at"])
            if expires < now:
                continue
        except Exception:
            continue
        if signal_types and s["type"] not in signal_types:
            continue
        signals.append(s)
    return signals


def clear_signal(source: str, signal_type: str) -> None:
    """Remove a specific signal (e.g., when it has been acted on)."""
    signals = [
        s for s in _load()
        if not (s["source"] == source and s["type"] == signal_type)
    ]
    _save(signals)


def format_signals_for_prompt(signals: list[dict]) -> str:
    """Format active signals as a concise prompt block."""
    if not signals:
        return ""
    lines = ["**Active cross-domain signals:**"]
    for s in signals:
        data_str = ", ".join(f"{k}={v}" for k, v in s.get("data", {}).items()) if s.get("data") else ""
        detail = f" ({data_str})" if data_str else ""
        lines.append(f"  • [{s['source']}] {s['type']}{detail}")
    return "\n".join(lines)
