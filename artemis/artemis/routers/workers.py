"""Worker agent endpoints.

POST /workers/{agent_id}/chat  — talk to a specific worker agent
GET  /workers                  — list all available workers + their status
GET  /workers/signals          — view active cross-domain signals
POST /workers/signals          — publish a signal (modules call this)
DELETE /workers/signals/{type} — clear a specific signal
"""
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from artemis.core.auth import validate_token
from artemis.core.registry import registry
from artemis.core.signals import (
    clear_signal,
    format_signals_for_prompt,
    get_active_signals,
    publish,
)
from artemis.core.workers import WORKER_REGISTRY

log = logging.getLogger("artemis.workers_router")
router = APIRouter(prefix="/workers", tags=["workers"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class WorkerChatRequest(BaseModel):
    message: str
    history: Optional[list] = None
    async_mode: bool = False


class SignalPublish(BaseModel):
    source: str
    signal_type: str
    data: Optional[dict] = None
    ttl_hours: int = 24


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_workers(token_payload: dict = Depends(validate_token)):
    """List all worker agents and their domain module health."""
    workers_info = []
    for agent_id, agent in WORKER_REGISTRY.items():
        module_health = {}
        for mod_id in agent.MODULE_IDS:
            mod = registry.get(mod_id)
            module_health[mod_id] = mod.healthy if mod else False

        workers_info.append({
            "id": agent_id,
            "name": agent.DOMAIN_NAME,
            "modules": agent.MODULE_IDS,
            "module_health": module_health,
            "all_modules_healthy": all(module_health.values()),
            "listens_to": agent.LISTENS_TO,
            "publishes": agent.PUBLISHES,
        })

    active_signals = get_active_signals()
    return {
        "workers": workers_info,
        "active_signals": len(active_signals),
    }


@router.post("/{agent_id}/chat")
async def worker_chat(
    agent_id: str,
    body: WorkerChatRequest,
    token_payload: dict = Depends(validate_token),
    authorization: Optional[str] = Header(None),
):
    """Send a message to a specific worker agent."""
    agent = WORKER_REGISTRY.get(agent_id)
    if not agent:
        available = list(WORKER_REGISTRY.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Worker '{agent_id}' not found. Available: {available}",
        )

    token = authorization.split(" ", 1)[1] if authorization else ""

    if body.async_mode:
        from fastapi import BackgroundTasks
        from common.tasks import enqueue, task

        # Can't inject BackgroundTasks in this path easily — run synchronously for now
        # TODO: wire async mode through BackgroundTasks dependency injection
        pass

    result = await agent.run(
        user_message=body.message,
        token_payload=token_payload,
        token=token,
        conversation_history=body.history,
    )

    return {
        "agent": agent_id,
        "domain": agent.DOMAIN_NAME,
        "response": result["response"],
        "tool_calls": result["tool_calls"],
    }


@router.get("/signals")
async def get_signals(
    signal_type: Optional[str] = None,
    token_payload: dict = Depends(validate_token),
):
    """View active cross-domain signals."""
    types = [signal_type] if signal_type else None
    signals = get_active_signals(signal_types=types)
    return {
        "signals": signals,
        "count": len(signals),
        "formatted": format_signals_for_prompt(signals),
    }


@router.post("/signals")
async def publish_signal(
    body: SignalPublish,
    token_payload: dict = Depends(validate_token),
):
    """Publish a signal from a module or worker agent."""
    publish(
        source=body.source,
        signal_type=body.signal_type,
        data=body.data,
        ttl_hours=body.ttl_hours,
    )
    return {"published": True, "source": body.source, "type": body.signal_type}


@router.delete("/signals/{signal_type}")
async def delete_signal(
    signal_type: str,
    source: Optional[str] = None,
    token_payload: dict = Depends(validate_token),
):
    """Clear a specific signal type (optionally from a specific source)."""
    if source:
        clear_signal(source, signal_type)
    else:
        # Clear all signals of this type from all sources
        signals = get_active_signals()
        for s in signals:
            if s["type"] == signal_type:
                clear_signal(s["source"], signal_type)
    return {"cleared": True, "type": signal_type}
