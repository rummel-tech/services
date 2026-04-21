"""Base class for Artemis worker agents.

Each worker is a domain expert who:
  - Speaks with a persona tuned for their domain
  - Has access only to their domain's module tools + memory tools
  - Publishes signals to the cross-agent bus
  - Reads relevant signals from other domains before responding
"""
import logging
from typing import Any, Dict, List, Optional

import anthropic

from artemis.core.memory import (
    get_context_for_prompt,
    get_todays_stoic_quote,
)
from artemis.core.persona import PERSONA_CORE
from artemis.core.registry import registry
from artemis.core.settings import get_settings
from artemis.core.signals import format_signals_for_prompt, get_active_signals

log = logging.getLogger("artemis.worker")

# Memory tools available to all workers (same as orchestrator)
from artemis.core.agent import MEMORY_TOOLS, _handle_memory_tool, _call_module_tool


class WorkerAgent:
    """Base class for domain worker agents."""

    # Subclasses define these
    AGENT_ID: str = "worker"
    DOMAIN_NAME: str = "General"
    MODULE_IDS: list[str] = []      # which modules this agent controls
    LISTENS_TO: list[str] = []       # signal types this agent reads from others
    PUBLISHES: list[str] = []        # signal types this agent may publish

    # Domain persona appended after the core Artemis character
    DOMAIN_PERSONA: str = ""

    async def run(
        self,
        user_message: str,
        token_payload: dict,
        token: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Run the worker agent loop. Returns {response, tool_calls}."""
        settings = get_settings()
        if not settings.anthropic_api_key:
            return {"response": "AI not configured — set ANTHROPIC_API_KEY.", "tool_calls": []}

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        # Build filtered tool set: only this domain's modules
        allowed = set(self.MODULE_IDS)
        module_tools = registry.build_claude_tools(allowed_modules=allowed)
        all_tools = module_tools + MEMORY_TOOLS

        # Assemble system prompt
        memory_ctx = get_context_for_prompt(max_chars=2000)
        quote = get_todays_stoic_quote()
        incoming_signals = get_active_signals(signal_types=self.LISTENS_TO)
        signal_block = format_signals_for_prompt(incoming_signals)
        user_name = token_payload.get("name") or "Shawn"
        modules_str = ", ".join(self.MODULE_IDS) or "none"

        from datetime import date
        today = str(date.today())

        system = self._build_prompt(
            user_name=user_name,
            today=today,
            modules=modules_str,
            memory_context=memory_ctx,
            signal_block=signal_block,
            stoic_quote=quote,
        )

        messages: List[Dict] = list(conversation_history or [])
        messages.append({"role": "user", "content": user_message})

        tool_calls_made: List[Dict] = []
        _MEMORY_TOOL_NAMES = {t["name"] for t in MEMORY_TOOLS}

        for _ in range(8):
            response = client.messages.create(
                model=settings.agent_model,
                max_tokens=2048,
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

                tool_calls_made.append({"tool": block.name, "input": block.input, "result": result})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                })

            messages.append({"role": "user", "content": tool_results})

        return {"response": "Worker reached maximum turns.", "tool_calls": tool_calls_made}

    def _build_prompt(
        self,
        user_name: str,
        today: str,
        modules: str,
        memory_context: str,
        signal_block: str,
        stoic_quote: Optional[dict] = None,
    ) -> str:
        quote_line = ""
        if stoic_quote:
            quote_line = f'\nToday\'s Stoic reflection: "{stoic_quote["text"]}" — {stoic_quote["author"]}\n'

        signals_section = f"\n{signal_block}\n" if signal_block else ""

        return f"""{PERSONA_CORE}

## You Are Currently Operating as the {self.DOMAIN_NAME} Agent

{self.DOMAIN_PERSONA}

## Session Context
Today: {today} | Speaking with: {user_name} | Your modules: {modules}
{quote_line}
## Persistent Memory
{memory_context}
{signals_section}"""
