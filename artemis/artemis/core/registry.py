"""Module registry — discovers and tracks Artemis-compatible modules.

On startup, polls each module's /artemis/manifest endpoint to build the
registry. Optionally refreshes in the background on a timer.
"""
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

from artemis.core.settings import get_settings

log = logging.getLogger("artemis.registry")


class RegisteredModule:
    """A live-registered Artemis module."""

    def __init__(self, module_id: str, manifest_url: str, enabled: bool = True) -> None:
        self.id = module_id
        self.manifest_url = manifest_url
        self.enabled = enabled
        self.manifest: Optional[Dict[str, Any]] = None
        self.healthy: bool = False
        self.last_checked: Optional[datetime] = None
        self.error: Optional[str] = None

    @property
    def api_base(self) -> Optional[str]:
        """Base URL of the module API, derived from manifest or manifest_url."""
        if self.manifest:
            return self.manifest.get("module", {}).get("api_base")
        # Fallback: strip /artemis/manifest from manifest_url
        return self.manifest_url.replace("/artemis/manifest", "")

    @property
    def agent_tools(self) -> List[Dict[str, Any]]:
        if not self.manifest:
            return []
        return self.manifest.get("capabilities", {}).get("agent_tools", [])

    @property
    def widgets(self) -> List[Dict[str, Any]]:
        if not self.manifest:
            return []
        return self.manifest.get("capabilities", {}).get("dashboard_widgets", [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "manifest_url": self.manifest_url,
            "enabled": self.enabled,
            "healthy": self.healthy,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "error": self.error,
            "manifest": self.manifest,
        }


class ModuleRegistry:
    """Registry of all Artemis platform modules."""

    def __init__(self) -> None:
        self._modules: Dict[str, RegisteredModule] = {}
        self._refresh_task: Optional[asyncio.Task] = None

    def _load_config(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        config_path = Path(settings.modules_config)
        if not config_path.is_absolute():
            config_path = Path.cwd() / config_path
        if not config_path.exists():
            log.warning(f"modules.yaml not found at {config_path}")
            return []
        with open(config_path) as f:
            data = yaml.safe_load(f)
        return data.get("modules", [])

    async def poll_module(self, module: RegisteredModule) -> None:
        """Fetch and cache a module's manifest."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(module.manifest_url)
                r.raise_for_status()
                module.manifest = r.json()
                module.healthy = True
                module.error = None
                log.info(f"registered module: {module.id} ({module.manifest_url})")
        except Exception as e:
            module.healthy = False
            module.error = str(e)
            log.warning(f"module {module.id} unavailable: {e}")
        finally:
            module.last_checked = datetime.now(timezone.utc)

    async def initialize(self) -> None:
        """Load config and poll all modules on startup."""
        entries = self._load_config()
        for entry in entries:
            if not entry.get("enabled", True):
                continue
            mod = RegisteredModule(
                module_id=entry["id"],
                manifest_url=entry["manifest_url"],
                enabled=True,
            )
            self._modules[mod.id] = mod

        # Poll all concurrently
        if self._modules:
            await asyncio.gather(*[self.poll_module(m) for m in self._modules.values()])

        settings = get_settings()
        if settings.registry_refresh_seconds > 0:
            self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def _refresh_loop(self) -> None:
        settings = get_settings()
        while True:
            await asyncio.sleep(settings.registry_refresh_seconds)
            await asyncio.gather(*[self.poll_module(m) for m in self._modules.values()])

    async def shutdown(self) -> None:
        if self._refresh_task:
            self._refresh_task.cancel()

    def get(self, module_id: str) -> Optional[RegisteredModule]:
        return self._modules.get(module_id)

    def list_modules(self) -> List[RegisteredModule]:
        return list(self._modules.values())

    def healthy_modules(self) -> List[RegisteredModule]:
        return [m for m in self._modules.values() if m.healthy]

    def build_claude_tools(self, allowed_modules: set = None) -> List[Dict[str, Any]]:
        """Auto-generate Claude tool definitions from module manifests.

        Tool name format: {module_id}__{tool_id}
        (double underscore so we can reverse-parse it)

        Args:
            allowed_modules: If non-empty, only include tools from these module IDs.
                             Empty set or None means include all healthy modules.
        """
        tools = []
        for mod in self.healthy_modules():
            if allowed_modules and mod.id not in allowed_modules:
                continue
            for tool in mod.agent_tools:
                params = tool.get("parameters", {})
                properties = {}
                required = []
                for param_name, param_def in params.items():
                    properties[param_name] = {
                        "type": param_def.get("type", "string"),
                        "description": param_def.get("description", ""),
                    }
                    if param_def.get("required", False):
                        required.append(param_name)

                tools.append({
                    "name": f"{mod.id.replace('-', '_')}__{tool['id']}",
                    "description": f"[{mod.id}] {tool['description']}",
                    "input_schema": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                })
        return tools

    def resolve_tool(self, tool_name: str) -> Optional[tuple[RegisteredModule, str]]:
        """Parse tool_name back into (module, tool_id)."""
        if "__" not in tool_name:
            return None
        module_key, tool_id = tool_name.split("__", 1)
        # Convert underscores back to hyphens for lookup
        module_id = module_key.replace("_", "-")
        mod = self._modules.get(module_id)
        if not mod:
            return None
        return mod, tool_id


# Global registry instance
registry = ModuleRegistry()
