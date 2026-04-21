"""Monitoring endpoints — visibility into background intelligence.

GET  /monitor/status          — current monitoring state + pending items
GET  /monitor/history         — last N monitoring run summaries
POST /monitor/run             — trigger an immediate monitoring cycle
GET  /monitor/notifications   — get unread proactive notifications
POST /monitor/notifications/read — mark all notifications as read
GET  /monitor/proposals       — list pending auto-scheduling proposals
POST /monitor/proposals/{id}/accept  — accept a proposal (creates task)
POST /monitor/proposals/{id}/reject  — reject a proposal
"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from artemis.core.auth import validate_token
from artemis.core.monitor import (
    add_proposal,
    get_monitor_history,
    get_pending_proposals,
    get_unread_notifications,
    mark_notifications_read,
    run_monitoring_cycle,
    update_proposal_status,
)
from artemis.core.registry import registry

log = logging.getLogger("artemis.monitor_router")
router = APIRouter(prefix="/monitor", tags=["monitor"])


@router.get("/status")
async def monitor_status(token_payload: dict = Depends(validate_token)):
    """Return monitoring state, pending proposals, and unread notifications."""
    notifications = get_unread_notifications()
    proposals = get_pending_proposals()
    history = get_monitor_history(n=1)
    last_run = history[-1] if history else None

    return {
        "unread_notifications": len(notifications),
        "pending_proposals": len(proposals),
        "last_run": last_run,
        "modules_healthy": len(registry.healthy_modules()),
        "modules_total": len(registry.list_modules()),
    }


@router.post("/run")
async def trigger_monitoring(token_payload: dict = Depends(validate_token)):
    """Trigger an immediate monitoring cycle (synchronous)."""
    summary = run_monitoring_cycle()
    return {"triggered": True, "summary": summary}


@router.get("/history")
async def monitor_history(
    n: int = 10,
    token_payload: dict = Depends(validate_token),
):
    """Return the last N monitoring run summaries."""
    return {"runs": get_monitor_history(n=n)}


@router.get("/notifications")
async def get_notifications(
    unread_only: bool = True,
    token_payload: dict = Depends(validate_token),
):
    """Return proactive notifications."""
    from artemis.core.monitor import _load_notifications
    notifs = get_unread_notifications() if unread_only else _load_notifications()
    return {"notifications": notifs, "count": len(notifs)}


@router.post("/notifications/read")
async def read_notifications(token_payload: dict = Depends(validate_token)):
    """Mark all notifications as read."""
    count = mark_notifications_read()
    return {"marked_read": count}


@router.get("/proposals")
async def list_proposals(
    status: Optional[str] = "pending",
    token_payload: dict = Depends(validate_token),
):
    """List auto-scheduling proposals."""
    from artemis.core.monitor import _load_proposals
    proposals = _load_proposals()
    if status:
        proposals = [p for p in proposals if p.get("status") == status]
    return {"proposals": proposals, "count": len(proposals)}


@router.post("/proposals/{proposal_id}/accept")
async def accept_proposal(
    proposal_id: str,
    token_payload: dict = Depends(validate_token),
    authorization: Optional[str] = Header(None),
):
    """Accept a proposal and execute its action (e.g. create a task)."""
    from artemis.core.monitor import _load_proposals

    proposals = _load_proposals()
    proposal = next((p for p in proposals if p["id"] == proposal_id), None)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Proposal is already {proposal['status']}")

    action = proposal.get("action")
    executed = False
    execution_result = None

    # Execute the action if it involves a module
    if action and action.get("type") == "create_task":
        module_id = action.get("module", "work-planner")
        mod = registry.get(module_id)
        if mod and mod.healthy:
            token = authorization.split(" ", 1)[1] if authorization else ""
            api_base = mod.api_base or mod.manifest_url.replace("/artemis/manifest", "")
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.post(
                        f"{api_base}/artemis/agent/create_task",
                        json=action.get("data", {}),
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if r.status_code in (200, 201):
                        executed = True
                        execution_result = r.json()
            except Exception as e:
                log.warning("proposal_execution_failed: %s", e)

    update_proposal_status(proposal_id, "accepted")

    return {
        "accepted": True,
        "proposal_id": proposal_id,
        "action_executed": executed,
        "result": execution_result,
    }


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: str,
    token_payload: dict = Depends(validate_token),
):
    """Reject a proposal."""
    updated = update_proposal_status(proposal_id, "rejected")
    if not updated:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return {"rejected": True, "proposal_id": proposal_id}
