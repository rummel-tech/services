"""Unified dashboard — aggregates widget data from all healthy modules."""
import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException

from artemis.core.auth import validate_token
from artemis.core.registry import registry

log = logging.getLogger("artemis.dashboard")
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


async def _fetch_widget(
    module_id: str,
    widget: Dict[str, Any],
    api_base: str,
    token: str,
) -> Dict[str, Any]:
    """Fetch a single widget's data from a module."""
    endpoint = widget.get("data_endpoint", "")
    url = f"{api_base}{endpoint}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            return {
                "module_id": module_id,
                "widget_id": widget["id"],
                "widget_name": widget.get("name"),
                "size": widget.get("size", "medium"),
                "data": r.json(),
                "error": None,
            }
    except Exception as e:
        log.warning(f"widget fetch failed {module_id}/{widget['id']}: {e}")
        return {
            "module_id": module_id,
            "widget_id": widget["id"],
            "widget_name": widget.get("name"),
            "size": widget.get("size", "medium"),
            "data": None,
            "error": str(e),
        }


@router.get("")
async def get_dashboard(
    token_payload: dict = Depends(validate_token),
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Return aggregated widget data from all healthy modules."""
    token = authorization.split(" ", 1)[1] if authorization else ""

    # Filter to modules the user has enabled (token.modules); empty list = all modules
    user_modules = set(token_payload.get("modules") or [])
    visible = [
        m for m in registry.healthy_modules()
        if not user_modules or m.id in user_modules
    ]

    fetch_tasks = []
    for mod in visible:
        api_base = mod.api_base or mod.manifest_url.replace("/artemis/manifest", "")
        for widget in mod.widgets:
            fetch_tasks.append(_fetch_widget(mod.id, widget, api_base, token))

    widgets = await asyncio.gather(*fetch_tasks)

    return {
        "user": {
            "id": token_payload.get("sub"),
            "name": token_payload.get("name"),
            "email": token_payload.get("email"),
        },
        "modules": {m.id: {"healthy": m.healthy} for m in registry.list_modules()},
        "widgets": list(widgets),
    }


@router.get("/widgets")
async def list_available_widgets(token: dict = Depends(validate_token)) -> List[Dict[str, Any]]:
    """List all available widgets from registered modules (without fetching data)."""
    user_modules = set(token.get("modules") or [])
    result = []
    for mod in registry.list_modules():
        if user_modules and mod.id not in user_modules:
            continue
        for widget in mod.widgets:
            result.append({
                "module_id": mod.id,
                "module_name": mod.manifest.get("module", {}).get("name") if mod.manifest else mod.id,
                **widget,
                "module_healthy": mod.healthy,
            })
    return result


async def _fetch_summary(module_id: str, api_base: str, token: str) -> Dict[str, Any]:
    """Fetch the optional /artemis/summary from a module."""
    url = f"{api_base}/artemis/summary"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            return {"module_id": module_id, "error": None, **r.json()}
    except Exception as e:
        log.warning(f"summary fetch failed {module_id}: {e}")
        return {"module_id": module_id, "summary": None, "data": None, "error": str(e)}


@router.get("/briefing")
async def get_briefing(
    token_payload: dict = Depends(validate_token),
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Aggregate natural language summaries from all healthy modules for AI daily briefings."""
    token = authorization.split(" ", 1)[1] if authorization else ""

    user_modules = set(token_payload.get("modules") or [])
    # Only include modules that advertise the optional summary endpoint
    candidates = [
        m for m in registry.healthy_modules()
        if (not user_modules or m.id in user_modules)
        and any(
            ep.get("path") == "/artemis/summary"
            for ep in (m.manifest or {}).get("capabilities", {}).get("optional_endpoints", [])
        )
    ]

    results = await asyncio.gather(
        *[_fetch_summary(m.id, m.api_base or m.manifest_url.replace("/artemis/manifest", ""), token) for m in candidates]
    )

    return {
        "user": {
            "id": token_payload.get("sub"),
            "name": token_payload.get("name"),
        },
        "summaries": list(results),
        "modules_included": len(results),
    }


async def _fetch_calendar(module_id: str, api_base: str, token: str) -> Dict[str, Any]:
    """Fetch the optional /artemis/calendar from a module."""
    url = f"{api_base}/artemis/calendar"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            return {"module_id": module_id, "error": None, **r.json()}
    except Exception as e:
        log.warning(f"calendar fetch failed {module_id}: {e}")
        return {"module_id": module_id, "events": [], "error": str(e)}


@router.get("/calendar")
async def get_calendar(
    token_payload: dict = Depends(validate_token),
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Aggregate and merge upcoming calendar events from all healthy modules."""
    token = authorization.split(" ", 1)[1] if authorization else ""

    user_modules = set(token_payload.get("modules") or [])
    # Only include modules that advertise the optional calendar endpoint
    candidates = [
        m for m in registry.healthy_modules()
        if (not user_modules or m.id in user_modules)
        and any(
            ep.get("path") == "/artemis/calendar"
            for ep in (m.manifest or {}).get("capabilities", {}).get("optional_endpoints", [])
        )
    ]

    results = await asyncio.gather(
        *[_fetch_calendar(m.id, m.api_base or m.manifest_url.replace("/artemis/manifest", ""), token) for m in candidates]
    )

    # Merge all events from all modules and sort by date ascending
    merged: List[Dict[str, Any]] = []
    for result in results:
        for event in result.get("events") or []:
            merged.append({"module_id": result["module_id"], **event})
    merged.sort(key=lambda e: e.get("date") or "")

    return {
        "user": {
            "id": token_payload.get("sub"),
            "name": token_payload.get("name"),
        },
        "events": merged,
        "modules_included": len(candidates),
        "window_days": 14,
    }


@router.get("/quick-actions")
async def list_quick_actions(token: dict = Depends(validate_token)) -> List[Dict[str, Any]]:
    """Aggregate quick actions from all healthy modules."""
    user_modules = set(token.get("modules") or [])
    result = []
    for mod in registry.healthy_modules():
        if user_modules and mod.id not in user_modules:
            continue
        actions = mod.manifest.get("capabilities", {}).get("quick_actions", []) if mod.manifest else []
        for action in actions:
            result.append({
                "module_id": mod.id,
                "api_base": mod.api_base,
                **action,
            })
    return result
