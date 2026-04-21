"""Life snapshot aggregator.

Polls all active module summary endpoints and merges with the running context
to produce a unified cross-domain snapshot. Used by the weekly synthesis and
pattern detector to see the full picture at once.
"""
import logging
from datetime import date, timedelta
from typing import Any, Optional

import httpx

from artemis.core.memory import load_running_context
from artemis.core.registry import registry
from artemis.core.signals import get_active_signals

log = logging.getLogger("artemis.aggregator")


async def _fetch_summary(module_id: str, token: str) -> Optional[str]:
    """GET /artemis/summary from a module. Returns natural language string or None."""
    mod = registry.get(module_id)
    if not mod or not mod.healthy:
        return None
    api_base = mod.api_base or mod.manifest_url.replace("/artemis/manifest", "")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{api_base}/artemis/summary",
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("summary") or data.get("text") or str(data)
    except Exception as e:
        log.debug("summary_fetch_failed module=%s err=%s", module_id, e)
    return None


async def _fetch_calendar(module_id: str, token: str, days: int = 14) -> list[dict]:
    """GET /artemis/calendar from a module."""
    mod = registry.get(module_id)
    if not mod or not mod.healthy:
        return []
    api_base = mod.api_base or mod.manifest_url.replace("/artemis/manifest", "")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{api_base}/artemis/calendar",
                params={"days": days},
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code == 200:
                return r.json() if isinstance(r.json(), list) else []
    except Exception:
        pass
    return []


DOMAIN_MODULES = {
    "body": ["workout-planner", "meal-planner"],
    "mind": ["education-planner", "content-planner"],
    "work": ["work-planner"],
    "home": ["home-manager", "vehicle-manager"],
    "travel": ["trip-planner"],
}


async def get_life_snapshot(token: str) -> dict[str, Any]:
    """Build a complete cross-domain snapshot by aggregating all sources."""
    ctx = load_running_context()
    signals = get_active_signals()

    domain_summaries: dict[str, str] = {}
    all_calendar: list[dict] = []

    for domain, modules in DOMAIN_MODULES.items():
        summaries = []
        for mod_id in modules:
            s = await _fetch_summary(mod_id, token)
            if s:
                summaries.append(s)
            cal = await _fetch_calendar(mod_id, token)
            all_calendar.extend(cal)

        if summaries:
            domain_summaries[domain] = " ".join(summaries)

    # Merge live summaries into context notes
    enriched_ctx = dict(ctx)
    for domain, summary in domain_summaries.items():
        if domain not in enriched_ctx:
            enriched_ctx[domain] = {}
        enriched_ctx[domain]["live_summary"] = summary

    return {
        "date": str(date.today()),
        "domains": enriched_ctx,
        "domain_summaries": domain_summaries,
        "active_signals": signals,
        "upcoming_events": sorted(all_calendar, key=lambda e: e.get("date", ""))[:20],
        "open_loops": ctx.get("open_loops", []),
    }


def format_snapshot_for_prompt(snapshot: dict) -> str:
    """Convert a life snapshot into a compact prompt-friendly string."""
    parts: list[str] = [f"Life Snapshot — {snapshot['date']}"]

    for domain, summary in snapshot.get("domain_summaries", {}).items():
        parts.append(f"**{domain.title()}:** {summary[:300]}")

    signals = snapshot.get("active_signals", [])
    if signals:
        sig_str = "; ".join(f"{s['source']}:{s['type']}" for s in signals[:6])
        parts.append(f"**Active signals:** {sig_str}")

    loops = snapshot.get("open_loops", [])
    if loops:
        parts.append(f"**Open loops ({len(loops)}):** {'; '.join(loops[:4])}")

    return "\n".join(parts)
