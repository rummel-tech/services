"""Morning and evening briefing endpoints.

GET /briefing/morning — pulls data from all modules, assembles a full day briefing
GET /briefing/evening — prompts the structured Stoic evening review
POST /briefing/evening — saves the completed evening review to session memory
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from artemis.core.auth import validate_token
from artemis.core.memory import (
    get_todays_stoic_quote,
    load_running_context,
    save_session,
    update_running_context,
)
from artemis.core.patterns import detect_patterns, format_patterns_for_briefing
from artemis.core.signals import get_active_signals, publish
from artemis.core.registry import registry

log = logging.getLogger("artemis.briefing")
router = APIRouter(prefix="/briefing", tags=["briefing"])


async def _fetch_module_summary(module_id: str, token: str) -> Optional[str]:
    """Fetch a natural-language summary from a module's /artemis/summary endpoint."""
    mod = registry.get(module_id)
    if not mod or not mod.healthy:
        return None

    api_base = mod.api_base or mod.manifest_url.replace("/artemis/manifest", "")
    url = f"{api_base}/artemis/summary"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 200:
                data = r.json()
                return data.get("summary") or str(data)
    except Exception as e:
        log.debug("summary fetch failed %s: %s", module_id, e)
    return None


async def _fetch_module_calendar(module_id: str, token: str) -> Optional[list]:
    """Fetch upcoming calendar events from a module."""
    mod = registry.get(module_id)
    if not mod or not mod.healthy:
        return None

    api_base = mod.api_base or mod.manifest_url.replace("/artemis/manifest", "")
    url = f"{api_base}/artemis/calendar"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return None


@router.get("/morning")
async def morning_briefing(
    token_payload: dict = Depends(validate_token),
    authorization: Optional[str] = Header(None),
):
    """Generate the morning briefing by pulling data from all active modules."""
    token = authorization.split(" ", 1)[1] if authorization else ""
    today = datetime.now(timezone.utc).date().isoformat()
    user_name = token_payload.get("name") or "Shawn"
    day_name = datetime.now(timezone.utc).strftime("%A")

    quote = get_todays_stoic_quote()
    ctx = load_running_context()

    # Pull summaries from each domain module
    module_summaries: dict[str, str] = {}
    domain_modules = {
        "body": ["workout-planner", "meal-planner"],
        "mind": ["education-planner", "content-planner"],
        "work": ["work-planner"],
        "home": ["home-manager", "vehicle-manager"],
        "travel": ["trip-planner"],
    }

    for domain, modules in domain_modules.items():
        for mod_id in modules:
            summary = await _fetch_module_summary(mod_id, token)
            if summary:
                existing = module_summaries.get(domain, "")
                module_summaries[domain] = (existing + " " + summary).strip()

    # Build sections
    sections: list[str] = []

    if module_summaries.get("body"):
        sections.append(f"**BODY**\n{module_summaries['body']}")
    elif ctx.get("body", {}).get("notes"):
        sections.append(f"**BODY**\n{ctx['body']['notes']}")

    if module_summaries.get("mind"):
        sections.append(f"**MIND**\n{module_summaries['mind']}")

    if module_summaries.get("work"):
        sections.append(f"**WORK**\n{module_summaries['work']}")
    else:
        work_ctx = ctx.get("work", {})
        if work_ctx.get("top_priority"):
            sections.append(f"**WORK**\nTop priority: {work_ctx['top_priority']}")

    if module_summaries.get("home"):
        sections.append(f"**HOME**\n{module_summaries['home']}")

    if module_summaries.get("travel"):
        sections.append(f"**TRAVEL**\n{module_summaries['travel']}")

    # Open loops
    open_loops = ctx.get("open_loops", [])
    if open_loops:
        loops_str = "\n".join(f"  • {l}" for l in open_loops[:5])
        sections.append(f"**OPEN LOOPS**\n{loops_str}")

    # Pattern detection — the cross-module intelligence layer
    signals = get_active_signals()
    # Merge live summaries into context for richer pattern detection
    enriched_ctx = dict(ctx)
    for domain, summary in module_summaries.items():
        enriched_ctx.setdefault(domain, {})["live_summary"] = summary
    patterns = detect_patterns(context=enriched_ctx, signals=signals)

    if patterns:
        # Auto-publish critical patterns as signals for workers to act on
        for p in patterns:
            if p.signal_to_publish and p.severity == "critical":
                source, sig_type, sig_data = p.signal_to_publish
                publish(source, sig_type, sig_data, ttl_hours=48)

        sections.append(format_patterns_for_briefing(patterns))

    # Stoic and reflection
    sections.append(
        f"**STOIC**\n\"{quote['text']}\"\n— {quote['author']}"
    )

    # Dynamic question — escalate if there's a critical pattern
    critical = next((p for p in patterns if p.severity == "critical"), None)
    if critical:
        sections.append(
            f"**ARTEMIS ASKS**\n{critical.message}"
        )
    else:
        sections.append(
            "**QUESTION FOR TODAY**\n"
            "What is the one thing, if done today, that would make everything else easier or unnecessary?"
        )

    briefing_text = "\n\n".join(sections)
    greeting = f"Good morning, {user_name}. {day_name}, {today}.\n\n{briefing_text}"

    return {
        "briefing": greeting,
        "date": today,
        "sections": {
            "body": module_summaries.get("body"),
            "mind": module_summaries.get("mind"),
            "work": module_summaries.get("work"),
            "home": module_summaries.get("home"),
            "travel": module_summaries.get("travel"),
        },
        "stoic_quote": quote,
        "open_loops": open_loops,
        "patterns": [
            {"name": p.name, "severity": p.severity, "headline": p.headline}
            for p in patterns
        ],
        "has_critical": any(p.severity == "critical" for p in patterns),
    }


@router.get("/evening")
async def evening_review_prompt(
    token_payload: dict = Depends(validate_token),
):
    """Return the structured evening review template."""
    user_name = token_payload.get("name") or "Shawn"

    return {
        "prompt": (
            f"Evening review — {datetime.now(timezone.utc).date().isoformat()}\n\n"
            "Answer each question briefly:\n\n"
            "1. **WINS** — What went well today?\n"
            "2. **MISSES** — What didn't get done? Carry forward or delete?\n"
            "3. **STOIC** — What could you have done better today?\n"
            "4. **BODY** — Did you hit your non-negotiables? (training, nutrition, sleep target)\n"
            "5. **REFLECTION** — What is one thing you learned or noticed about yourself?\n"
            "6. **GRATITUDE** — What are you genuinely grateful for?\n"
            "7. **TOMORROW** — What is your top priority for tomorrow?\n"
        ),
        "fields": [
            "wins", "misses", "stoic_reflection",
            "body_non_negotiables", "insight", "gratitude", "tomorrow_priority"
        ],
    }


class EveningReviewInput(BaseModel):
    wins: Optional[str] = None
    misses: Optional[str] = None
    stoic_reflection: Optional[str] = None
    body_non_negotiables: Optional[str] = None
    insight: Optional[str] = None
    gratitude: Optional[str] = None
    tomorrow_priority: Optional[str] = None


@router.post("/evening")
async def save_evening_review(
    body: EveningReviewInput,
    token_payload: dict = Depends(validate_token),
):
    """Save the completed evening review to session memory."""
    today = datetime.now(timezone.utc).date().isoformat()

    md_lines = [f"# Evening Review — {today}\n"]
    field_labels = {
        "wins": "Wins",
        "misses": "Misses / Carry-forward",
        "stoic_reflection": "Stoic Reflection",
        "body_non_negotiables": "Body Non-Negotiables",
        "insight": "Insight",
        "gratitude": "Gratitude",
        "tomorrow_priority": "Tomorrow's Top Priority",
    }
    for field, label in field_labels.items():
        value = getattr(body, field)
        if value:
            md_lines.append(f"## {label}\n{value}\n")

    summary = "\n".join(md_lines)
    path = save_session(summary, date=today)

    # Update running context with spirit practice streak
    update_running_context({"spirit": {"last_evening_review": today}})

    return {"saved": True, "path": str(path), "date": today}
