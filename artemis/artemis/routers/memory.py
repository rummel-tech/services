"""Memory management endpoints.

GET  /memory/vision           — read life vision document
PUT  /memory/vision           — overwrite life vision document
GET  /memory/context          — read running context JSON
PUT  /memory/context          — deep-merge updates into running context
GET  /memory/sessions         — list recent session summaries
GET  /memory/sessions/{date}  — read a specific session
GET  /memory/insights         — list insight files
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from artemis.core.auth import validate_token
from artemis.core.memory import (
    SESSIONS_DIR,
    INSIGHTS_DIR,
    load_life_vision,
    load_recent_sessions,
    load_running_context,
    save_life_vision,
    save_insight,
    update_running_context,
)

log = logging.getLogger("artemis.memory_router")
router = APIRouter(prefix="/memory", tags=["memory"])


# ---------------------------------------------------------------------------
# Life Vision
# ---------------------------------------------------------------------------

@router.get("/vision")
async def get_vision(token_payload: dict = Depends(validate_token)):
    """Return the Life Vision Document as markdown."""
    return {"content": load_life_vision(), "format": "markdown"}


class VisionUpdate(BaseModel):
    content: str


@router.put("/vision")
async def update_vision(body: VisionUpdate, token_payload: dict = Depends(validate_token)):
    """Overwrite the Life Vision Document."""
    save_life_vision(body.content)
    return {"saved": True, "length": len(body.content)}


# ---------------------------------------------------------------------------
# Running Context
# ---------------------------------------------------------------------------

@router.get("/context")
async def get_context(token_payload: dict = Depends(validate_token)):
    """Return the full running context JSON."""
    return load_running_context()


class ContextUpdate(BaseModel):
    updates: dict[str, Any]


@router.put("/context")
async def patch_context(body: ContextUpdate, token_payload: dict = Depends(validate_token)):
    """Deep-merge updates into the running context."""
    update_running_context(body.updates)
    return {"updated": True}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@router.get("/sessions")
async def list_sessions(
    n: int = 10,
    token_payload: dict = Depends(validate_token),
):
    """List recent session summaries."""
    sessions = load_recent_sessions(n=n)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/sessions/{date}")
async def get_session(date: str, token_payload: dict = Depends(validate_token)):
    """Read a specific session log by date (YYYY-MM-DD)."""
    path = SESSIONS_DIR / f"{date}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No session found for {date}")
    return {"date": date, "content": path.read_text(encoding="utf-8")}


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

@router.get("/insights")
async def list_insights(token_payload: dict = Depends(validate_token)):
    """List all insight files."""
    files = list(INSIGHTS_DIR.glob("*.md"))
    return {
        "insights": [
            {
                "category": f.stem,
                "preview": f.read_text(encoding="utf-8")[:300],
            }
            for f in sorted(files)
        ]
    }


class InsightInput(BaseModel):
    text: str
    category: str = "general"


@router.post("/insights")
async def add_insight(body: InsightInput, token_payload: dict = Depends(validate_token)):
    """Manually capture an insight."""
    save_insight(body.text, body.category)
    return {"saved": True}
