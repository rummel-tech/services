"""Claude AI agent for the Artemis platform.

Tools are auto-generated from module manifests at runtime.
When Claude calls a tool, the platform proxies the request to the appropriate
module's /artemis/agent/{tool_id} endpoint, forwarding the user's Artemis token.
"""
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import anthropic
import httpx

from artemis.core.registry import ModuleRegistry, registry
from artemis.core.settings import get_settings

log = logging.getLogger("artemis.agent")

SYSTEM_PROMPT = """You are Artemis, a personal AI assistant that helps manage your life across multiple domains: fitness, nutrition, home, vehicles, work, finance, and more.

You have access to tools from multiple personal management modules. Use them to answer questions, take actions, and provide insights. Always be concise and helpful.

When you need information from a module, call the appropriate tool. Combine data from multiple modules when relevant (e.g., correlate workout intensity with nutrition).

Today's date: {today}
User: {user_name}
Enabled modules: {modules}
"""


def _build_system_prompt(payload: dict) -> str:
    from datetime import date
    return SYSTEM_PROMPT.format(
        today=str(date.today()),
        user_name=payload.get("name") or payload.get("email", "User"),
        modules=", ".join(payload.get("modules", [])) or "none configured",
    )


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

    # Find the tool's method and endpoint from the manifest
    tool_def = next((t for t in mod.agent_tools if t["id"] == tool_id), None)
    if not tool_def:
        return {"error": f"Tool {tool_id} not found in {module_id}"}

    method = tool_def.get("method", "POST").upper()
    endpoint = tool_def.get("endpoint", f"/artemis/agent/{tool_id}")

    # Build URL from api_base in manifest
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
        log.warning(f"tool call failed {module_id}/{tool_id}: {e.response.status_code}")
        return {"error": f"Module returned {e.response.status_code}"}
    except Exception as e:
        log.warning(f"tool call error {module_id}/{tool_id}: {e}")
        return {"error": str(e)}


async def run_agent(
    user_message: str,
    token_payload: dict,
    token: str,
    conversation_history: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Run the agent with a user message. Returns the final text response.

    Handles the full agentic loop: Claude → tool calls → results → Claude.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {
            "response": "AI agent not configured — set ANTHROPIC_API_KEY.",
            "tool_calls": [],
        }

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    tools = registry.build_claude_tools()
    system = _build_system_prompt(token_payload)

    messages: List[Dict] = list(conversation_history or [])
    messages.append({"role": "user", "content": user_message})

    tool_calls_made: List[Dict] = []

    for _ in range(8):  # max 8 agentic turns
        response = client.messages.create(
            model=settings.agent_model,
            max_tokens=2048,
            system=system,
            tools=tools if tools else anthropic.NOT_GIVEN,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            text = next(
                (b.text for b in response.content if hasattr(b, "text")), ""
            )
            return {"response": text, "tool_calls": tool_calls_made}

        if response.stop_reason != "tool_use":
            text = next(
                (b.text for b in response.content if hasattr(b, "text")), ""
            )
            return {"response": text, "tool_calls": tool_calls_made}

        # Process tool calls
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue

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
    """Stream agent response as server-sent events (text/event-stream)."""
    result = await run_agent(user_message, token_payload, token)
    # Yield the final text in chunks for now
    # TODO: wire up streaming SDK when needed
    text = result["response"]
    chunk_size = 40
    for i in range(0, len(text), chunk_size):
        yield f"data: {text[i:i+chunk_size]}\n\n"
    yield "data: [DONE]\n\n"
