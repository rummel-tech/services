"""Life synthesis endpoints — weekly review and quarterly vision.

GET  /synthesis/snapshot           — full cross-domain life snapshot
GET  /synthesis/weekly             — generate this week's review
POST /synthesis/weekly             — save the completed weekly review
GET  /synthesis/quarterly          — generate quarterly review against life vision
POST /synthesis/quarterly/update   — update vision document with quarterly insights
GET  /synthesis/patterns           — run pattern detector, return active patterns
"""
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from artemis.core.aggregator import format_snapshot_for_prompt, get_life_snapshot
from artemis.core.auth import validate_token
from artemis.core.memory import (
    load_life_vision,
    load_recent_sessions,
    load_running_context,
    save_insight,
    save_life_vision,
    save_session,
    update_running_context,
)
from artemis.core.patterns import detect_patterns, format_patterns_for_briefing
from artemis.core.signals import get_active_signals

log = logging.getLogger("artemis.synthesis")
router = APIRouter(prefix="/synthesis", tags=["synthesis"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _week_bounds() -> tuple[str, str]:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return str(monday), str(sunday)


def _quarter_bounds() -> tuple[str, str]:
    today = date.today()
    q = (today.month - 1) // 3
    q_start = date(today.year, q * 3 + 1, 1)
    if q == 3:
        q_end = date(today.year, 12, 31)
    else:
        q_end = date(today.year, (q + 1) * 3 + 1, 1) - timedelta(days=1)
    return str(q_start), str(q_end)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/snapshot")
async def life_snapshot(
    token_payload: dict = Depends(validate_token),
    authorization: Optional[str] = Header(None),
):
    """Pull a full cross-domain life snapshot from all active modules."""
    token = authorization.split(" ", 1)[1] if authorization else ""
    snapshot = await get_life_snapshot(token)
    patterns = detect_patterns(
        context=snapshot["domains"],
        signals=snapshot["active_signals"],
    )
    return {
        **snapshot,
        "patterns": [
            {
                "name": p.name,
                "severity": p.severity,
                "domains": p.domains,
                "headline": p.headline,
                "message": p.message,
            }
            for p in patterns
        ],
        "patterns_formatted": format_patterns_for_briefing(patterns),
    }


@router.get("/patterns")
async def get_patterns(token_payload: dict = Depends(validate_token)):
    """Run the pattern detector against current context and signals. No modules polled."""
    ctx = load_running_context()
    signals = get_active_signals()
    patterns = detect_patterns(context=ctx, signals=signals)

    return {
        "patterns": [
            {
                "name": p.name,
                "severity": p.severity,
                "domains": p.domains,
                "headline": p.headline,
                "message": p.message,
            }
            for p in patterns
        ],
        "count": len(patterns),
        "formatted": format_patterns_for_briefing(patterns),
        "has_critical": any(p.severity == "critical" for p in patterns),
        "has_warning": any(p.severity == "warning" for p in patterns),
    }


@router.get("/weekly")
async def weekly_review(
    token_payload: dict = Depends(validate_token),
    authorization: Optional[str] = Header(None),
):
    """Generate this week's cross-domain review with prompts for each domain."""
    token = authorization.split(" ", 1)[1] if authorization else ""
    monday, sunday = _week_bounds()
    ctx = load_running_context()
    snapshot = await get_life_snapshot(token)
    patterns = detect_patterns(context=snapshot["domains"], signals=snapshot["active_signals"])

    # Build domain scorecards
    body = ctx.get("body", {})
    work = ctx.get("work", {})
    mind = ctx.get("mind", {})
    spirit = ctx.get("spirit", {})

    body_pct = None
    if body.get("weekly_workouts_completed") and body.get("weekly_workouts_target"):
        body_pct = round((body["weekly_workouts_completed"] / body["weekly_workouts_target"]) * 100)

    work_pct = None
    if work.get("deep_work_hours_this_week") and work.get("deep_work_target_hours"):
        work_pct = round((work["deep_work_hours_this_week"] / work["deep_work_target_hours"]) * 100)

    review = {
        "week": {"start": monday, "end": sunday},
        "scorecards": {
            "body": {
                "workout_completion_pct": body_pct,
                "readiness": body.get("current_readiness"),
                "nutrition_on_track": body.get("nutrition_on_track"),
            },
            "work": {
                "deep_work_pct": work_pct,
                "goal_completion": work.get("goal_completion_this_week"),
                "top_priority_moved": None,  # populated by user in POST
            },
            "mind": {
                "content_queue_depth": mind.get("content_queue_depth"),
                "learning_goal_active": mind.get("active_learning_goal"),
            },
            "spirit": {
                "morning_streak": spirit.get("morning_practice_streak"),
                "evening_streak": spirit.get("evening_review_streak"),
                "sabbath": spirit.get("sabbath_observed_last_week"),
            },
        },
        "active_patterns": [
            {"name": p.name, "severity": p.severity, "headline": p.headline}
            for p in patterns
        ],
        "domain_summaries": snapshot.get("domain_summaries", {}),
        "open_loops": ctx.get("open_loops", []),
        "prompts": {
            "wins": "What were the 3 most important things accomplished this week?",
            "misses": "What was planned that didn't happen? Why?",
            "body": "Did you keep your physical non-negotiables? What was the impact?",
            "mind": "What was the most valuable thing learned this week?",
            "work": "Did your work move the needle on what actually matters?",
            "spirit": "Were you the person you want to be this week?",
            "next_week": "What is the single most important focus for next week?",
            "pattern_reflection": format_patterns_for_briefing(patterns) if patterns else None,
        },
    }

    return review


class WeeklyReviewSave(BaseModel):
    wins: Optional[str] = None
    misses: Optional[str] = None
    body_reflection: Optional[str] = None
    mind_reflection: Optional[str] = None
    work_reflection: Optional[str] = None
    spirit_reflection: Optional[str] = None
    next_week_focus: Optional[str] = None
    next_week_intentions: Optional[str] = None
    # Scorecard updates
    workout_completion_pct: Optional[int] = None
    deep_work_hours: Optional[float] = None
    goal_completion: Optional[int] = None


@router.post("/weekly")
async def save_weekly_review(
    body: WeeklyReviewSave,
    token_payload: dict = Depends(validate_token),
):
    """Save the completed weekly review and update running context for next week."""
    monday, sunday = _week_bounds()
    today = str(date.today())

    # Build markdown summary
    lines = [f"# Weekly Review — {monday} to {sunday}\n"]
    field_map = {
        "wins": "Wins",
        "misses": "Misses",
        "body_reflection": "Body",
        "mind_reflection": "Mind",
        "work_reflection": "Work",
        "spirit_reflection": "Spirit",
        "next_week_focus": "Next Week Focus",
        "next_week_intentions": "Next Week Intentions",
    }
    for field, label in field_map.items():
        val = getattr(body, field)
        if val:
            lines.append(f"## {label}\n{val}\n")

    session_text = "\n".join(lines)
    save_session(session_text, date=today)

    # Reset weekly counters in running context for the new week
    ctx_updates: dict = {}
    if body.deep_work_hours is not None:
        ctx_updates["work"] = {"deep_work_hours_this_week": 0}
    if body.goal_completion is not None:
        ctx_updates.setdefault("work", {})["goal_completion_this_week"] = 0
    if body.next_week_focus:
        ctx_updates.setdefault("work", {})["top_priority"] = body.next_week_focus

    # Reset body weekly counters
    ctx_updates["body"] = {"weekly_workouts_completed": 0}

    if ctx_updates:
        update_running_context(ctx_updates)

    # Capture any standout insights
    if body.wins:
        save_insight(f"Week of {monday}: {body.wins}", category="patterns")
    if body.next_week_focus:
        save_insight(f"Week of {monday} focus: {body.next_week_focus}", category="decisions")

    return {
        "saved": True,
        "week": monday,
        "context_reset": list(ctx_updates.keys()),
    }


@router.get("/quarterly")
async def quarterly_review(
    token_payload: dict = Depends(validate_token),
    authorization: Optional[str] = Header(None),
):
    """Generate a quarterly review comparing current state against the life vision."""
    token = authorization.split(" ", 1)[1] if authorization else ""
    q_start, q_end = _quarter_bounds()
    vision = load_life_vision()
    ctx = load_running_context()
    snapshot = await get_life_snapshot(token)
    patterns = detect_patterns(context=snapshot["domains"], signals=snapshot["active_signals"])

    # Pull last 12 weeks of sessions for trend
    recent_sessions = load_recent_sessions(n=12)

    # Build review structure
    review = {
        "quarter": {"start": q_start, "end": q_end},
        "vision_document": vision,
        "current_state": ctx,
        "active_patterns": [
            {"name": p.name, "severity": p.severity, "headline": p.headline, "message": p.message}
            for p in patterns
        ],
        "session_count_this_quarter": len(recent_sessions),
        "prompts": {
            "vision_gap": (
                "Looking at your Life Vision Document: which domain has drifted "
                "furthest from where you said you wanted to be?"
            ),
            "biggest_win": "What is the single biggest accomplishment of this quarter?",
            "biggest_miss": "What commitment did you make that you didn't keep? What did that cost?",
            "what_worked": "What system or habit most reliably delivered results this quarter?",
            "what_failed": "What did you try that didn't work? What will you stop?",
            "next_quarter_focus": (
                "If you could only move one needle next quarter — body, mind, work, "
                "spirit, or wealth — which one has the highest leverage on everything else?"
            ),
            "vision_update": "Does your vision document need updating? What has changed in how you see the future?",
            "stoic_reflection": (
                "'When you wake up in the morning, tell yourself: The people I deal with "
                "today will be meddling, ungrateful, arrogant, dishonest, jealous and surly.' "
                "— Marcus Aurelius. What external circumstances defined this quarter that "
                "were outside your control? How did you respond?"
            ),
        },
        "pattern_analysis": format_patterns_for_briefing(patterns) if patterns else "No significant patterns detected.",
    }

    return review


class QuarterlyVisionUpdate(BaseModel):
    biggest_win: Optional[str] = None
    biggest_miss: Optional[str] = None
    next_quarter_focus: Optional[str] = None
    vision_updates: Optional[str] = None  # Markdown to append to vision doc
    domain_updates: Optional[dict] = None  # Running context updates


@router.post("/quarterly/update")
async def save_quarterly_update(
    body: QuarterlyVisionUpdate,
    token_payload: dict = Depends(validate_token),
):
    """Save quarterly insights and optionally update the life vision document."""
    q_start, _ = _quarter_bounds()
    today = str(date.today())

    # Save as session
    lines = [f"# Quarterly Review — {q_start}\n"]
    if body.biggest_win:
        lines.append(f"## Biggest Win\n{body.biggest_win}\n")
        save_insight(body.biggest_win, category="patterns")
    if body.biggest_miss:
        lines.append(f"## Biggest Miss\n{body.biggest_miss}\n")
    if body.next_quarter_focus:
        lines.append(f"## Next Quarter Focus\n{body.next_quarter_focus}\n")
        save_insight(body.next_quarter_focus, category="decisions")
    if body.vision_updates:
        lines.append(f"## Vision Updates\n{body.vision_updates}\n")

    save_session("\n".join(lines), date=today)

    # Append to vision doc if updates provided
    if body.vision_updates:
        vision = load_life_vision()
        updated_vision = (
            vision.rstrip()
            + f"\n\n---\n\n## Quarterly Update — {q_start}\n{body.vision_updates}\n"
        )
        save_life_vision(updated_vision)

    # Update running context
    if body.domain_updates:
        update_running_context(body.domain_updates)

    return {"saved": True, "quarter": q_start, "vision_updated": bool(body.vision_updates)}
