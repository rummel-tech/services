"""External agent spawning — research, document summarization, and web search.

Artemis can spawn specialized sub-agents for tasks beyond its core modules:

  ResearchAgent   — deep-dive on any topic via web search or knowledge
  SummarizeAgent  — extract key insights from documents, articles, PDFs
  FinanceAgent    — market data, investment analysis (future)

These are implemented as focused Claude agent calls with specialized tools.
The orchestrator can call them as needed during a conversation.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import anthropic

from artemis.core.settings import get_settings

log = logging.getLogger("artemis.external_agents")

# ---------------------------------------------------------------------------
# Research Agent
# ---------------------------------------------------------------------------

_RESEARCH_PERSONA = """You are a world-class research agent.
Your job is to give Shawn a thorough, honest, well-sourced answer to his question.
You think in first principles. You distinguish facts from interpretations.
You cite sources when using web search. You are concise but complete.
Format: lead with the direct answer, then supporting evidence, then implications.
Never pad. If you don't know something, say so."""

_SUMMARIZE_PERSONA = """You are a precision document analyst.
Your job is to extract the most valuable signal from any text.
Format your output as:
  ## Core Idea (1 sentence)
  ## Key Insights (3-5 bullet points — each a complete, actionable idea)
  ## What This Means for Shawn (1-2 sentences connecting to his goals)
  ## One Question This Raises (the most useful question the material opens up)
Never summarize for completeness. Extract for value."""


def _web_search_tools() -> list[dict]:
    """Return Anthropic native web search tool if available."""
    return [
        {
            "type": "web_search_20250305",
            "name": "web_search",
        }
    ]


async def research(
    query: str,
    context: Optional[str] = None,
    use_web: bool = True,
) -> dict[str, Any]:
    """Run a focused research query. Returns {answer, sources, model_used}."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {"answer": "Research agent not configured — set ANTHROPIC_API_KEY.", "sources": []}

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    context_block = f"\n\nContext: {context}" if context else ""
    user_msg = f"Research this thoroughly: {query}{context_block}"

    try:
        tools = _web_search_tools() if use_web else []

        kwargs: dict = {
            "model": settings.agent_model,
            "max_tokens": 2048,
            "system": _RESEARCH_PERSONA,
            "messages": [{"role": "user", "content": user_msg}],
        }
        if tools:
            kwargs["tools"] = tools
            # Web search requires beta header
            extra_headers = {"anthropic-beta": "web-search-2025-03-05"}
        else:
            extra_headers = {}

        response = client.messages.create(**kwargs, extra_headers=extra_headers)

        # Extract text and any source citations
        text_parts = [b.text for b in response.content if hasattr(b, "text")]
        answer = "\n".join(text_parts).strip()

        # Extract web search result citations if present
        sources = []
        for block in response.content:
            if hasattr(block, "type") and block.type == "tool_result":
                # Web search results embedded in tool_result blocks
                sources.extend(_extract_sources(block))

        return {
            "answer": answer,
            "sources": sources,
            "model_used": settings.agent_model,
            "web_search_used": bool(tools),
        }

    except anthropic.BadRequestError:
        # Web search unavailable — fall back to knowledge-only
        log.info("web_search_unavailable — falling back to knowledge-only research")
        return await research(query, context, use_web=False)

    except Exception as e:
        log.exception("research_agent_error query=%s", query[:80])
        return {"answer": f"Research failed: {str(e)}", "sources": []}


def _extract_sources(block: Any) -> list[dict]:
    """Extract source URLs from a web search tool_result block."""
    try:
        content = block.content if hasattr(block, "content") else []
        sources = []
        for item in (content if isinstance(content, list) else []):
            if isinstance(item, dict) and item.get("type") == "web_search_result":
                sources.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                })
        return sources
    except Exception:
        return []


async def summarize(
    text: str,
    source_name: Optional[str] = None,
    user_context: Optional[str] = None,
) -> dict[str, Any]:
    """Summarize a document or article and extract key insights."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {"summary": "Summarizer not configured.", "insights": []}

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    source_label = f" from '{source_name}'" if source_name else ""
    context_block = f"\n\nUser context: {user_context}" if user_context else ""

    # Truncate very long texts
    truncated = text[:8000] + ("... [truncated]" if len(text) > 8000 else "")

    response = client.messages.create(
        model=settings.agent_model,
        max_tokens=1024,
        system=_SUMMARIZE_PERSONA,
        messages=[{
            "role": "user",
            "content": (
                f"Summarize this document{source_label}:{context_block}\n\n"
                f"---\n{truncated}\n---"
            )
        }],
    )

    summary_text = next(
        (b.text for b in response.content if hasattr(b, "text")), ""
    ).strip()

    # Parse out insights list for structured return
    insights = _parse_insights(summary_text)

    return {
        "summary": summary_text,
        "insights": insights,
        "source": source_name,
        "model_used": settings.agent_model,
        "char_count": len(text),
    }


def _parse_insights(text: str) -> list[str]:
    """Extract bullet-pointed insights from a summary response."""
    insights = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith(("- ", "• ", "* ")) and len(line) > 10:
            insights.append(line.lstrip("-•* "))
    return insights[:6]


# ---------------------------------------------------------------------------
# Continuous improvement agent
# ---------------------------------------------------------------------------

async def suggest_platform_improvements(
    failed_tool_calls: list[dict],
    missing_capabilities: list[str],
) -> list[dict]:
    """Analyze failed/missing tool calls and suggest GitHub issues.

    Returns a list of {title, body, labels} dicts ready to create as issues.
    """
    settings = get_settings()
    if not settings.anthropic_api_key or not failed_tool_calls and not missing_capabilities:
        return []

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    items = []
    for fc in failed_tool_calls[:5]:
        items.append(f"- Tool call failed: {fc.get('tool')} with input {str(fc.get('input', {}))[:100]}")
    for cap in missing_capabilities[:5]:
        items.append(f"- Missing capability: {cap}")

    if not items:
        return []

    response = client.messages.create(
        model=settings.agent_model,
        max_tokens=1024,
        system=(
            "You are a platform architect reviewing gaps in a personal AI OS. "
            "Given a list of failed tool calls and missing capabilities, "
            "generate concise GitHub issue titles and bodies. "
            "Format: JSON array of {title, body, labels} objects. "
            "Labels should be one of: enhancement, bug, agent-capability. "
            "Be specific and actionable."
        ),
        messages=[{
            "role": "user",
            "content": f"Generate GitHub issues for these gaps:\n" + "\n".join(items)
        }],
    )

    text = next((b.text for b in response.content if hasattr(b, "text")), "[]")

    try:
        # Try to parse JSON from the response
        import json, re
        json_match = re.search(r'\[.*?\]', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception:
        pass

    return []
