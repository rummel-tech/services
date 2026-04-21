"""Claude AI agent for the Artemis platform.

Tools are auto-generated from module manifests at runtime.
When Claude calls a tool, the platform proxies the request to the appropriate
module's /artemis/agent/{tool_id} endpoint, forwarding the user's Artemis token.
"""
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import anthropic
import httpx

from artemis.core.memory import (
    get_context_for_prompt,
    get_todays_stoic_quote,
    save_session,
    save_insight,
    update_running_context,
    add_open_loop,
    close_open_loop,
    vision_needs_intake,
)
from artemis.core.persona import build_system_prompt
from artemis.core.signals import format_signals_for_prompt, get_active_signals, publish
from artemis.core.registry import ModuleRegistry, registry
from artemis.core.settings import get_settings

log = logging.getLogger("artemis.agent")


# ---------------------------------------------------------------------------
# Memory tools — Claude can call these to persist insights mid-session
# ---------------------------------------------------------------------------

MEMORY_TOOLS = [
    {
        "name": "save_session_summary",
        "description": (
            "Save a summary of this conversation to persistent memory. "
            "Call this at the END of each session to capture: what was discussed, "
            "decisions made, insights gained, and open loops remaining. "
            "This is how Artemis remembers across sessions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Structured markdown summary: ## What Was Discussed, ## Decisions Made, ## Insights, ## Open Loops"
                }
            },
            "required": ["summary"]
        }
    },
    {
        "name": "capture_insight",
        "description": "Capture a meaningful insight, pattern, or realization about Shawn for long-term memory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "insight": {"type": "string", "description": "The insight to capture"},
                "category": {
                    "type": "string",
                    "description": "Category: 'patterns', 'decisions', 'health', 'work', 'philosophy', 'general'",
                    "default": "general"
                }
            },
            "required": ["insight"]
        }
    },
    {
        "name": "update_domain_context",
        "description": "Update the running context for a specific life domain. Use this when Shawn shares new information about his current state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "One of: body, mind, work, home, travel, spirit, wealth"
                },
                "updates": {
                    "type": "object",
                    "description": "Key-value pairs to update in that domain (e.g. {\"current_book\": \"Meditations\"})"
                }
            },
            "required": ["domain", "updates"]
        }
    },
    {
        "name": "add_open_loop",
        "description": "Add an open loop (uncommitted action) to track.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {"type": "string", "description": "The open loop to track"}
            },
            "required": ["item"]
        }
    },
    {
        "name": "close_open_loop",
        "description": "Mark an open loop as complete and remove it from tracking.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {"type": "string", "description": "The open loop to close"}
            },
            "required": ["item"]
        }
    },
    {
        "name": "publish_signal",
        "description": (
            "Publish a cross-domain signal to alert other worker agents. "
            "Use this when you detect a pattern that another domain should know about. "
            "Examples: low_readiness (Body→Work), deadline_approaching (Work→Body/Mind), "
            "trip_upcoming (Travel→all), environment_friction (Home→all)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "signal_type": {
                    "type": "string",
                    "description": "The signal type (e.g. low_readiness, deadline_approaching, trip_upcoming)"
                },
                "source": {
                    "type": "string",
                    "description": "Which agent is publishing (e.g. body, work, travel, home, mind, orchestrator)"
                },
                "data": {
                    "type": "object",
                    "description": "Optional structured data (e.g. {score: 58, days: 3})"
                },
                "ttl_hours": {
                    "type": "number",
                    "description": "Hours until signal expires. Default 24.",
                    "default": 24
                }
            },
            "required": ["signal_type", "source"]
        }
    }
]


def _handle_memory_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a memory tool call locally."""
    try:
        if tool_name == "save_session_summary":
            path = save_session(tool_input["summary"])
            return {"saved": True, "path": str(path)}

        if tool_name == "capture_insight":
            save_insight(
                text=tool_input["insight"],
                category=tool_input.get("category", "general")
            )
            return {"saved": True}

        if tool_name == "update_domain_context":
            update_running_context({tool_input["domain"]: tool_input["updates"]})
            return {"updated": True}

        if tool_name == "add_open_loop":
            add_open_loop(tool_input["item"])
            return {"added": True}

        if tool_name == "close_open_loop":
            close_open_loop(tool_input["item"])
            return {"closed": True}

        if tool_name == "publish_signal":
            publish(
                source=tool_input["source"],
                signal_type=tool_input["signal_type"],
                data=tool_input.get("data"),
                ttl_hours=int(tool_input.get("ttl_hours", 24)),
            )
            return {"published": True}

        return {"error": f"Unknown memory tool: {tool_name}"}
    except Exception as e:
        log.exception("memory_tool_error tool=%s", tool_name)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Module tool execution
# ---------------------------------------------------------------------------

async def _call_module_tool(
    module_id: str,
    tool_id: str,
    tool_input: Dict[str, Any],
    token: str,
) -> Dict[str, Any]:
    """Proxy a tool call to the appropriate module endpoint."""
    mod = registry.get(module_id)
    if not mod or not mod.healthy:
        return {"error": f"Module {module_id} is unavailable"}

    tool_def = next((t for t in mod.agent_tools if t["id"] == tool_id), None)
    if not tool_def:
        return {"error": f"Tool {tool_id} not found in {module_id}"}

    method = tool_def.get("method", "POST").upper()
    endpoint = tool_def.get("endpoint", f"/artemis/agent/{tool_id}")
    api_base = mod.api_base or mod.manifest_url.replace("/artemis/manifest", "")
    url = f"{api_base}{endpoint}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if method == "GET":
                r = await client.get(url, params=tool_input, headers=headers)
            else:
                r = await client.post(url, json=tool_input, headers=headers)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        log.warning("tool_call_failed %s/%s: %s", module_id, tool_id, e.response.status_code)
        return {"error": f"Module returned {e.response.status_code}"}
    except Exception as e:
        log.warning("tool_call_error %s/%s: %s", module_id, tool_id, e)
        return {"error": str(e)}


async def _call_platform_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    dev_tools: Any,
) -> Dict[str, Any]:
    """Execute a platform__ tool locally via DevTools."""
    if dev_tools is None:
        return {"error": "Platform tools not configured — set GITHUB_TOKEN."}

    op = tool_name.removeprefix("platform__")

    if op == "list_issues":
        return await dev_tools.list_issues(
            repo=tool_input.get("repo", "services"),
            state=tool_input.get("state", "open"),
        )
    if op == "create_issue":
        return await dev_tools.create_issue(
            repo=tool_input.get("repo", "services"),
            title=tool_input["title"],
            body=tool_input["body"],
            labels=tool_input.get("labels"),
        )
    if op == "deployment_status":
        return await dev_tools.get_deployment_status(service=tool_input.get("service", "artemis"))
    if op == "trigger_deployment":
        return await dev_tools.trigger_deployment(
            service=tool_input["service"],
            environment=tool_input.get("environment", "staging"),
        )
    return {"error": f"Unknown platform tool: {op}"}


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

async def run_agent(
    user_message: str,
    token_payload: dict,
    token: str,
    conversation_history: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Run the Artemis agent. Returns final text + tool call log."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {
            "response": "AI agent not configured — set ANTHROPIC_API_KEY.",
            "tool_calls": [],
        }

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_modules = set(token_payload.get("modules") or [])
    module_tools = registry.build_claude_tools(allowed_modules=user_modules)

    # Platform self-management tools
    dev_tools = None
    platform_tools = []
    if settings.github_token:
        from artemis.core.dev_tools import DevTools, build_platform_tools
        dev_tools = DevTools(settings.github_token, settings.github_org)
        platform_tools = build_platform_tools()

    all_tools = module_tools + platform_tools + MEMORY_TOOLS

    # Build persona system prompt with injected memory + active signals
    memory_context = get_context_for_prompt()
    stoic_quote = get_todays_stoic_quote()
    needs_intake = vision_needs_intake()
    active_signals = get_active_signals()
    signal_block = format_signals_for_prompt(active_signals)

    # Append signal context to memory block so Artemis sees cross-domain state
    full_memory = memory_context
    if signal_block:
        full_memory = memory_context + f"\n\n{signal_block}"

    system = build_system_prompt(
        token_payload=token_payload,
        memory_context=full_memory,
        stoic_quote=stoic_quote,
        needs_intake=needs_intake,
    )

    messages: List[Dict] = list(conversation_history or [])
    messages.append({"role": "user", "content": user_message})

    tool_calls_made: List[Dict] = []
    _MEMORY_TOOL_NAMES = {t["name"] for t in MEMORY_TOOLS}

    for _ in range(10):  # max 10 agentic turns
        response = client.messages.create(
            model=settings.agent_model,
            max_tokens=4096,
            system=system,
            tools=all_tools if all_tools else anthropic.NOT_GIVEN,
            messages=messages,
        )

        if response.stop_reason in ("end_turn", None):
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            return {"response": text, "tool_calls": tool_calls_made}

        if response.stop_reason != "tool_use":
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            return {"response": text, "tool_calls": tool_calls_made}

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name in _MEMORY_TOOL_NAMES:
                result = _handle_memory_tool(block.name, block.input)
            elif block.name.startswith("platform__"):
                result = await _call_platform_tool(block.name, block.input, dev_tools)
            else:
                resolved = registry.resolve_tool(block.name)
                if not resolved:
                    result = {"error": f"Unknown tool: {block.name}"}
                else:
                    module, tool_id = resolved
                    result = await _call_module_tool(
                        module_id=module.id,
                        tool_id=tool_id,
                        tool_input=block.input,
                        token=token,
                    )

            tool_calls_made.append({
                "tool": block.name,
                "input": block.input,
                "result": result,
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result),
            })

        messages.append({"role": "user", "content": tool_results})

    return {"response": "Agent reached maximum turns.", "tool_calls": tool_calls_made}


async def stream_agent(
    user_message: str,
    token_payload: dict,
    token: str,
) -> AsyncIterator[str]:
    """Stream agent response as server-sent events."""
    result = await run_agent(user_message, token_payload, token)
    text = result["response"]
    chunk_size = 40
    for i in range(0, len(text), chunk_size):
        yield f"data: {text[i:i+chunk_size]}\n\n"
    yield "data: [DONE]\n\n"
