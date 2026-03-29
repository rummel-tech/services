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

    fetch_tasks = []
    for mod in registry.healthy_modules():
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
    result = []
    for mod in registry.list_modules():
        for widget in mod.widgets:
            result.append({
                "module_id": mod.id,
                "module_name": mod.manifest.get("module", {}).get("name") if mod.manifest else mod.id,
                **widget,
                "module_healthy": mod.healthy,
            })
    return result


@router.get("/quick-actions")
async def list_quick_actions(token: dict = Depends(validate_token)) -> List[Dict[str, Any]]:
    """Aggregate quick actions from all healthy modules."""
    result = []
    for mod in registry.healthy_modules():
        actions = mod.manifest.get("capabilities", {}).get("quick_actions", []) if mod.manifest else []
        for action in actions:
            result.append({
                "module_id": mod.id,
                "api_base": mod.api_base,
                **action,
            })
    return result
