"""Background monitoring — proactive intelligence without waiting to be asked.

Runs as an asyncio background task alongside the registry refresh loop.
Every monitoring cycle it:
  1. Detects cross-domain patterns from the running context + signal bus
  2. Auto-publishes signals for critical patterns
  3. Queues push notifications for anything actionable
  4. Pre-generates the morning briefing if it's the right time
  5. Surfaces open loops that have been sitting too long
  6. Logs the monitoring run for transparency

The monitor intentionally does NOT call live module APIs — it works from the
running context and signal bus only, keeping it fast and side-effect-free.
Module data is pulled lazily when the briefing is requested.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from artemis.core.goal_evolution import (
    get_dormant_goals,
    scan_sessions_for_mentions,
    sync_from_running_context,
)
from artemis.core.memory import (
    MEMORY_DIR,
    load_running_context,
    save_insight,
    update_running_context,
)
from artemis.core.outcomes import snapshot_outcome_from_context
from artemis.core.patterns import detect_patterns
from artemis.core.signals import get_active_signals, publish

log = logging.getLogger("artemis.monitor")

# Paths
NOTIFICATIONS_FILE = MEMORY_DIR / "notifications.json"
PROPOSALS_FILE = MEMORY_DIR / "proposals.json"
MONITOR_LOG_FILE = MEMORY_DIR / "monitor_log.json"
BRIEFINGS_DIR = MEMORY_DIR / "briefings"

# Monitoring intervals
MONITOR_INTERVAL_SECONDS = 4 * 3600   # every 4 hours
MORNING_BRIEFING_HOUR = 5             # pre-generate briefing at 5am local
OPEN_LOOP_ALERT_DAYS = 7              # surface open loops older than this

_monitor_task: Optional[asyncio.Task] = None


# ---------------------------------------------------------------------------
# Notification queue
# ---------------------------------------------------------------------------

def _load_notifications() -> list[dict]:
    if not NOTIFICATIONS_FILE.exists():
        return []
    try:
        return json.loads(NOTIFICATIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_notifications(notifications: list[dict]) -> None:
    NOTIFICATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    NOTIFICATIONS_FILE.write_text(
        json.dumps(notifications, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def push_notification(
    title: str,
    body: str,
    severity: str = "info",
    domain: Optional[str] = None,
    action: Optional[str] = None,
) -> None:
    """Add a notification to the queue."""
    notifications = _load_notifications()
    notifications.append({
        "id": f"notif_{datetime.now(timezone.utc).timestamp():.0f}",
        "title": title,
        "body": body,
        "severity": severity,
        "domain": domain,
        "action": action,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "read": False,
    })
    # Keep only last 50
    _save_notifications(notifications[-50:])


def get_unread_notifications() -> list[dict]:
    return [n for n in _load_notifications() if not n.get("read")]


def mark_notifications_read() -> int:
    notifications = _load_notifications()
    count = 0
    for n in notifications:
        if not n.get("read"):
            n["read"] = True
            count += 1
    _save_notifications(notifications)
    return count


# ---------------------------------------------------------------------------
# Proposal queue (auto-scheduling suggestions)
# ---------------------------------------------------------------------------

def _load_proposals() -> list[dict]:
    if not PROPOSALS_FILE.exists():
        return []
    try:
        return json.loads(PROPOSALS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_proposals(proposals: list[dict]) -> None:
    PROPOSALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROPOSALS_FILE.write_text(
        json.dumps(proposals, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def add_proposal(
    proposal_type: str,
    title: str,
    description: str,
    action: Optional[dict] = None,
    domain: str = "work",
) -> dict:
    """Add an auto-scheduling proposal. Returns the proposal dict."""
    proposals = _load_proposals()
    proposal = {
        "id": f"prop_{datetime.now(timezone.utc).timestamp():.0f}",
        "type": proposal_type,
        "title": title,
        "description": description,
        "domain": domain,
        "action": action,
        "status": "pending",      # pending | accepted | rejected
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Remove duplicate proposals of the same type
    proposals = [p for p in proposals if p.get("type") != proposal_type]
    proposals.append(proposal)
    _save_proposals(proposals[-20:])
    return proposal


def get_pending_proposals() -> list[dict]:
    return [p for p in _load_proposals() if p.get("status") == "pending"]


def update_proposal_status(proposal_id: str, status: str) -> bool:
    proposals = _load_proposals()
    for p in proposals:
        if p["id"] == proposal_id:
            p["status"] = status
            p["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_proposals(proposals)
            return True
    return False


# ---------------------------------------------------------------------------
# Monitor log
# ---------------------------------------------------------------------------

def _log_run(summary: dict) -> None:
    log_entries: list[dict] = []
    if MONITOR_LOG_FILE.exists():
        try:
            log_entries = json.loads(MONITOR_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            log_entries = []

    summary["timestamp"] = datetime.now(timezone.utc).isoformat()
    log_entries.append(summary)
    log_entries = log_entries[-100:]  # keep last 100 runs
    MONITOR_LOG_FILE.write_text(
        json.dumps(log_entries, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_monitor_history(n: int = 10) -> list[dict]:
    if not MONITOR_LOG_FILE.exists():
        return []
    try:
        entries = json.loads(MONITOR_LOG_FILE.read_text(encoding="utf-8"))
        return entries[-n:]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Core monitoring logic
# ---------------------------------------------------------------------------

def run_monitoring_cycle() -> dict:
    """Execute one monitoring cycle. Returns a summary of what was done.

    This is synchronous so it can be called from tests and from the API.
    The background loop calls it via asyncio.to_thread.
    """
    ctx = load_running_context()
    signals = get_active_signals()
    patterns = detect_patterns(context=ctx, signals=signals)
    today = str(date.today())

    actions_taken: list[str] = []
    notifications_pushed: int = 0
    proposals_added: int = 0
    signals_published: int = 0

    # 1. Process patterns → signals + notifications
    for pattern in patterns:
        if pattern.signal_to_publish and pattern.severity in ("critical", "warning"):
            source, sig_type, sig_data = pattern.signal_to_publish
            publish(source, sig_type, sig_data, ttl_hours=24)
            signals_published += 1
            actions_taken.append(f"published signal {sig_type}")

        if pattern.severity == "critical":
            push_notification(
                title=f"Artemis Alert: {pattern.headline}",
                body=pattern.message[:280],
                severity="critical",
                domain=pattern.domains[0] if pattern.domains else None,
                action=f"review_{pattern.name}",
            )
            notifications_pushed += 1
            actions_taken.append(f"notification: {pattern.headline}")

    # 2. Auto-scheduling proposals

    # Deep work deficit → propose protected morning block
    work = ctx.get("work", {})
    dw_hours = work.get("deep_work_hours_this_week", 0) or 0
    dw_target = work.get("deep_work_target_hours", 20) or 20
    if dw_target > 0 and (dw_hours / dw_target) < 0.5:
        prop = add_proposal(
            proposal_type="deep_work_block",
            title="Protect tomorrow morning for deep work",
            description=(
                f"Deep work is at {dw_hours:.0f}/{dw_target:.0f} hours this week "
                f"({dw_hours/dw_target*100:.0f}% of target). "
                "Blocking 9am–12pm tomorrow for uninterrupted focus."
            ),
            action={
                "type": "create_task",
                "module": "work-planner",
                "data": {
                    "title": "🔒 Deep Work Block — Protected",
                    "priority": "urgent",
                    "category": "deep_work",
                    "scheduled_time": "09:00",
                    "duration_minutes": 180,
                }
            },
            domain="work",
        )
        proposals_added += 1
        actions_taken.append("proposal: deep work block")

    # Body recovery needed → propose rest day
    body = ctx.get("body", {})
    readiness = body.get("current_readiness")
    if readiness is not None and readiness < 60:
        add_proposal(
            proposal_type="recovery_day",
            title="Schedule an active recovery day tomorrow",
            description=(
                f"Readiness is {readiness} — below the recovery threshold. "
                "Proposing a low-intensity recovery session instead of a planned workout."
            ),
            action={
                "type": "create_task",
                "module": "work-planner",
                "data": {
                    "title": "🔄 Active Recovery — Walk/Stretch Only",
                    "priority": "high",
                    "category": "health",
                    "duration_minutes": 45,
                }
            },
            domain="body",
        )
        proposals_added += 1
        actions_taken.append("proposal: recovery day")

    # Open loop surface — flag loops with no recent activity
    open_loops = ctx.get("open_loops", [])
    if len(open_loops) >= 5:
        push_notification(
            title=f"Open Loop Check: {len(open_loops)} items need a decision",
            body=(
                f"You have {len(open_loops)} open loops. "
                "Each is a background tax on your attention. "
                f"Top items: {'; '.join(open_loops[:3])}"
            ),
            severity="info",
            domain="work",
            action="review_open_loops",
        )
        notifications_pushed += 1
        actions_taken.append(f"notification: {len(open_loops)} open loops")

    # 3. Spirit practice streak alert
    spirit = ctx.get("spirit", {})
    if spirit.get("morning_practice_streak", 0) == 0 and spirit.get("evening_review_streak", 0) == 0:
        push_notification(
            title="Practice Streak Broken",
            body="Both morning Stoic practice and evening review streaks are at zero. One session resets the momentum — start tomorrow morning with 5 minutes.",
            severity="warning",
            domain="spirit",
            action="start_morning_practice",
        )
        notifications_pushed += 1
        actions_taken.append("notification: practice streak broken")

    # 4. Phase 5 — auto-snapshot outcomes and scan goal health
    try:
        snapshot_outcome_from_context()
        actions_taken.append("outcome snapshot captured")
    except Exception as e:
        log.warning("outcome_snapshot_failed: %s", e)

    try:
        sync_from_running_context()
        scan_sessions_for_mentions()
    except Exception as e:
        log.warning("goal_scan_failed: %s", e)

    # Surface dormant goals for review
    dormant = get_dormant_goals()
    if dormant:
        titles = ", ".join(g["title"] for g in dormant[:3])
        push_notification(
            title=f"{len(dormant)} goal(s) have gone dormant",
            body=(
                f"These goals have had no progress in 22+ days: {titles}. "
                "Retire, revive, or evolve them — drift happens gradually then all at once."
            ),
            severity="info",
            domain="work",
            action="review_dormant_goals",
        )
        notifications_pushed += 1
        actions_taken.append(f"flagged {len(dormant)} dormant goals")

    summary = {
        "date": today,
        "patterns_detected": len(patterns),
        "critical_patterns": sum(1 for p in patterns if p.severity == "critical"),
        "warning_patterns": sum(1 for p in patterns if p.severity == "warning"),
        "signals_published": signals_published,
        "notifications_pushed": notifications_pushed,
        "proposals_added": proposals_added,
        "dormant_goals": len(dormant),
        "actions": actions_taken,
    }
    _log_run(summary)
    log.info(
        "monitoring_cycle patterns=%d signals=%d notifications=%d proposals=%d",
        len(patterns), signals_published, notifications_pushed, proposals_added,
    )
    return summary


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------

async def _monitoring_loop() -> None:
    """Long-running asyncio task that calls run_monitoring_cycle periodically."""
    log.info("monitoring loop started (interval=%ds)", MONITOR_INTERVAL_SECONDS)
    while True:
        try:
            await asyncio.to_thread(run_monitoring_cycle)
        except Exception:
            log.exception("monitoring_cycle_error")
        await asyncio.sleep(MONITOR_INTERVAL_SECONDS)


def start_monitoring() -> None:
    """Start the background monitoring loop. Call from app startup."""
    global _monitor_task
    if _monitor_task is None or _monitor_task.done():
        _monitor_task = asyncio.create_task(_monitoring_loop())
        log.info("background monitor started")


def stop_monitoring() -> None:
    """Cancel the monitoring loop. Call from app shutdown."""
    global _monitor_task
    if _monitor_task and not _monitor_task.done():
        _monitor_task.cancel()
        _monitor_task = None
        log.info("background monitor stopped")
