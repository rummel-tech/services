"""External agent endpoints — research, summarization, continuous improvement.

POST /research/query      — deep research on any topic
POST /research/summarize  — extract key insights from text/document
POST /research/improve    — suggest GitHub issues from tool failures
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from artemis.core.auth import validate_token
from artemis.core.external_agents import research, summarize, suggest_platform_improvements

log = logging.getLogger("artemis.research_router")
router = APIRouter(prefix="/research", tags=["research"])


class ResearchRequest(BaseModel):
    query: str
    context: Optional[str] = None
    use_web: bool = True


class SummarizeRequest(BaseModel):
    text: str
    source_name: Optional[str] = None
    context: Optional[str] = None


class ImprovementRequest(BaseModel):
    failed_tool_calls: list[dict] = []
    missing_capabilities: list[str] = []


@router.post("/query")
async def run_research(
    body: ResearchRequest,
    token_payload: dict = Depends(validate_token),
):
    """Spawn a research agent to answer a question with optional web search."""
    result = await research(
        query=body.query,
        context=body.context,
        use_web=body.use_web,
    )
    return result


@router.post("/summarize")
async def run_summarize(
    body: SummarizeRequest,
    token_payload: dict = Depends(validate_token),
):
    """Extract key insights from a document or article."""
    result = await summarize(
        text=body.text,
        source_name=body.source_name,
        user_context=body.context,
    )
    return result


@router.post("/improve")
async def continuous_improvement(
    body: ImprovementRequest,
    token_payload: dict = Depends(validate_token),
):
    """Analyze tool failures and missing capabilities — return GitHub issue suggestions."""
    issues = await suggest_platform_improvements(
        failed_tool_calls=body.failed_tool_calls,
        missing_capabilities=body.missing_capabilities,
    )
    return {"issues": issues, "count": len(issues)}
