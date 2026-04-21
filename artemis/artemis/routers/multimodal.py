"""Multi-modal endpoints — voice-optimized briefing, widget data, shareable digest.

GET  /multimodal/briefing/voice      — voice-friendly briefing (no markdown)
GET  /multimodal/widget              — compact JSON for iOS widget
GET  /multimodal/digest/weekly       — shareable weekly summary (markdown)
POST /multimodal/voice-input         — receive transcribed audio, route to agent
"""
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from artemis.core.agent import run_agent
from artemis.core.auth import validate_token
from artemis.core.memory import (
    get_todays_stoic_quote,
    load_recent_sessions,
    load_running_context,
)
from artemis.core.monitor import get_pending_proposals, get_unread_notifications
from artemis.core.patterns import detect_patterns
from artemis.core.signals import get_active_signals

log = logging.getLogger("artemis.multimodal_router")
router = APIRouter(prefix="/multimodal", tags=["multimodal"])


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting for voice output."""
    import re
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"#{1,6} +", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"^\s*[•\-\*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@router.get("/briefing/voice")
async def voice_briefing(token_payload: dict = Depends(validate_token)):
    """Voice-friendly briefing: plain prose, no markdown, conversational sentences."""
    user_name = token_payload.get("name") or "Shawn"
    today = date.today()
    day_name = today.strftime("%A")

    ctx = load_running_context()
    quote = get_todays_stoic_quote()
    signals = get_active_signals()
    patterns = detect_patterns(context=ctx, signals=signals)

    body = ctx.get("body", {})
    work = ctx.get("work", {})

    parts = [f"Good morning {user_name}. It's {day_name}, {today.strftime('%B %d')}."]

    readiness = body.get("current_readiness")
    if readiness is not None:
        tier = (
            "excellent" if readiness >= 80
            else "good" if readiness >= 65
            else "moderate" if readiness >= 50
            else "low"
        )
        parts.append(f"Your readiness is {readiness}, which is {tier}.")

    top = work.get("top_priority")
    if top:
        parts.append(f"Your top priority today is: {top}.")

    critical = next((p for p in patterns if p.severity == "critical"), None)
    if critical:
        parts.append(
            f"Before anything else, I need your attention on this: {_strip_markdown(critical.message)}"
        )
    elif patterns:
        top_pattern = patterns[0]
        parts.append(f"One thing I'm tracking: {top_pattern.headline}. {_strip_markdown(top_pattern.message)}")

    parts.append(f"Today's reflection from {quote['author']}: {quote['text']}")

    if not critical:
        parts.append(
            "Here's the question to sit with today. "
            "What is the one thing, if done today, that would make everything else easier or unnecessary?"
        )

    spoken = " ".join(parts)

    return {
        "spoken_text": spoken,
        "estimated_duration_seconds": len(spoken.split()) / 2.5,
        "date": today.isoformat(),
    }


@router.get("/widget")
async def widget_data(token_payload: dict = Depends(validate_token)):
    """Minimal JSON for an iOS/Android home-screen widget."""
    ctx = load_running_context()
    quote = get_todays_stoic_quote()
    signals = get_active_signals()
    patterns = detect_patterns(context=ctx, signals=signals)
    notifications = get_unread_notifications()
    proposals = get_pending_proposals()

    body = ctx.get("body", {})
    work = ctx.get("work", {})
    spirit = ctx.get("spirit", {})

    severity_color = "green"
    if any(p.severity == "critical" for p in patterns):
        severity_color = "red"
    elif any(p.severity == "warning" for p in patterns) or len(notifications) > 0:
        severity_color = "amber"

    return {
        "date": date.today().isoformat(),
        "status_color": severity_color,
        "readiness": body.get("current_readiness"),
        "top_priority": work.get("top_priority"),
        "workouts": {
            "completed": body.get("weekly_workouts_completed"),
            "target": body.get("weekly_workouts_target"),
        },
        "streaks": {
            "morning": spirit.get("morning_practice_streak", 0),
            "evening": spirit.get("evening_review_streak", 0),
        },
        "counts": {
            "notifications": len(notifications),
            "proposals": len(proposals),
            "open_loops": len(ctx.get("open_loops", [])),
        },
        "top_pattern": (
            {
                "headline": patterns[0].headline,
                "severity": patterns[0].severity,
            }
            if patterns else None
        ),
        "stoic_quote": {"text": quote["text"][:100], "author": quote["author"]},
    }


@router.get("/digest/weekly")
async def weekly_digest(token_payload: dict = Depends(validate_token)):
    """Shareable weekly summary (markdown, safe for email/sharing)."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    ctx = load_running_context()
    sessions = load_recent_sessions(n=7)
    patterns = detect_patterns(context=ctx, signals=get_active_signals())

    body = ctx.get("body", {})
    work = ctx.get("work", {})
    spirit = ctx.get("spirit", {})

    lines = [
        f"# Week of {monday.strftime('%B %d')} — Artemis Digest",
        "",
        "## Scorecard",
        "",
        f"- Workouts: {body.get('weekly_workouts_completed', 0)} / {body.get('weekly_workouts_target', 5)}",
        f"- Deep work: {work.get('deep_work_hours_this_week', 0):.1f} / {work.get('deep_work_target_hours', 20)}h",
        f"- Goals completed: {work.get('goal_completion_this_week', 0)}",
        f"- Morning practice streak: {spirit.get('morning_practice_streak', 0)} days",
        f"- Evening review streak: {spirit.get('evening_review_streak', 0)} days",
        "",
    ]

    if patterns:
        lines.append("## What Artemis Is Tracking")
        lines.append("")
        for p in patterns[:3]:
            lines.append(f"**{p.headline}** — {p.message}")
            lines.append("")

    if sessions:
        lines.append("## Session Highlights")
        lines.append("")
        for s in sessions[:3]:
            preview = s.get("content", "")[:200].replace("\n", " ")
            lines.append(f"- **{s.get('date')}**: {preview}...")
        lines.append("")

    open_loops = ctx.get("open_loops", [])
    if open_loops:
        lines.append("## Open Loops")
        lines.append("")
        for loop in open_loops[:5]:
            lines.append(f"- {loop}")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by Artemis — your personal operating system.*")

    return {
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "markdown": "\n".join(lines),
    }


class VoiceInput(BaseModel):
    transcription: str
    history: Optional[list] = None


@router.post("/voice-input")
async def voice_input(
    body: VoiceInput,
    token_payload: dict = Depends(validate_token),
    authorization: Optional[str] = Header(None),
):
    """Receive a voice transcription and route it to the Artemis agent."""
    token = authorization.split(" ", 1)[1] if authorization else ""
    result = await run_agent(
        user_message=body.transcription,
        token_payload=token_payload,
        token=token,
        conversation_history=body.history,
    )
    spoken = _strip_markdown(result.get("response", ""))
    return {
        "response": result["response"],
        "spoken_text": spoken,
        "tool_calls": result.get("tool_calls", []),
    }
