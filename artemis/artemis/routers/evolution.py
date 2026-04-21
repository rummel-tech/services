"""Pattern learning + goal evolution endpoints.

GET  /evolution/outcomes              — recent daily outcomes
POST /evolution/outcomes              — log today's outcome manually
POST /evolution/outcomes/snapshot     — auto-capture from running context
GET  /evolution/correlations          — what actually works for Shawn
GET  /evolution/goals                 — all goals with health status
POST /evolution/goals                 — register a new goal
POST /evolution/goals/{id}/progress   — mark progress on a goal
POST /evolution/goals/{id}/retire     — retire a goal
GET  /evolution/goals/dormant         — goals needing review
POST /evolution/goals/scan            — scan sessions for mentions + sync from context
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from artemis.core.auth import validate_token
from artemis.core.goal_evolution import (
    get_dormant_goals,
    get_goal_health,
    mark_progress,
    register_goal,
    retire_goal,
    scan_sessions_for_mentions,
    sync_from_running_context,
)
from artemis.core.outcomes import (
    analyze_patterns,
    load_recent_outcomes,
    log_daily_outcome,
    snapshot_outcome_from_context,
)

log = logging.getLogger("artemis.evolution_router")
router = APIRouter(prefix="/evolution", tags=["evolution"])


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------

@router.get("/outcomes")
async def get_outcomes(
    days: int = 30,
    token_payload: dict = Depends(validate_token),
):
    entries = load_recent_outcomes(n_days=days)
    return {"count": len(entries), "outcomes": entries}


class OutcomeInput(BaseModel):
    day: Optional[str] = None
    inputs: Optional[dict] = None
    outcomes: Optional[dict] = None


@router.post("/outcomes")
async def save_outcome(
    body: OutcomeInput,
    token_payload: dict = Depends(validate_token),
):
    entry = log_daily_outcome(day=body.day, inputs=body.inputs, outcomes=body.outcomes)
    return {"saved": True, "entry": entry}


@router.post("/outcomes/snapshot")
async def snapshot_outcome(token_payload: dict = Depends(validate_token)):
    """Auto-capture today's outcome from the running context."""
    entry = snapshot_outcome_from_context()
    return {"captured": True, "entry": entry}


@router.get("/correlations")
async def get_correlations(
    days: int = 60,
    min_sample: int = 5,
    token_payload: dict = Depends(validate_token),
):
    """Run correlation analysis across inputs and outcomes."""
    return analyze_patterns(n_days=days, min_sample=min_sample)


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

@router.get("/goals")
async def list_goals(token_payload: dict = Depends(validate_token)):
    return {"goals": get_goal_health()}


@router.get("/goals/dormant")
async def list_dormant(token_payload: dict = Depends(validate_token)):
    dormant = get_dormant_goals()
    return {"dormant": dormant, "count": len(dormant)}


class GoalInput(BaseModel):
    id: str
    title: str
    domain: str = "work"


@router.post("/goals")
async def add_goal(
    body: GoalInput,
    token_payload: dict = Depends(validate_token),
):
    goal = register_goal(body.id, body.title, body.domain)
    return {"registered": True, "goal": goal}


@router.post("/goals/{goal_id}/progress")
async def record_progress(
    goal_id: str,
    token_payload: dict = Depends(validate_token),
):
    mark_progress(goal_id)
    return {"recorded": True}


class RetireInput(BaseModel):
    reason: Optional[str] = None


@router.post("/goals/{goal_id}/retire")
async def retire(
    goal_id: str,
    body: RetireInput,
    token_payload: dict = Depends(validate_token),
):
    ok = retire_goal(goal_id, body.reason)
    if not ok:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"retired": True}


@router.post("/goals/scan")
async def scan_goals(token_payload: dict = Depends(validate_token)):
    registered = sync_from_running_context()
    updated = scan_sessions_for_mentions()
    return {"registered_from_context": registered, "mentions_updated": updated}
