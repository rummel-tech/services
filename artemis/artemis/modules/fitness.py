"""Fitness tracking module for Artemis personal OS."""
from datetime import date, timedelta
from typing import Any, Dict
from artemis.core.module import BaseModule, ModuleConfig, ModuleStatus, ModuleSummary, QuickAction
from artemis.core.client import ServiceClient
from artemis.core.settings import settings


class FitnessModule(BaseModule):
    """Module for tracking fitness activities and health metrics.

    Proxies requests to the workout-planner backend service.

    Features:
    - Workout logging
    - Exercise tracking
    - Fitness goal setting
    - Progress monitoring
    """

    def __init__(self, config: ModuleConfig) -> None:
        """Initialize the fitness module."""
        super().__init__(config)
        self.client = ServiceClient(settings.services.workout_planner_url)

    async def initialize(self) -> None:
        """Initialize the fitness module."""
        # Check backend service health
        self._initialized = await self.client.health_check()

    async def shutdown(self) -> None:
        """Shutdown the fitness module."""
        await self.client.close()
        self._initialized = False
    
    async def get_status(self) -> ModuleStatus:
        """Get the current status of the fitness module."""
        healthy = await self.client.health_check()

        # Note: workout-planner requires authentication
        # For now, report service health only
        return ModuleStatus(
            name=self.name,
            enabled=self.is_enabled,
            healthy=healthy,
            message="Connected to workout-planner service" if healthy else "Workout-planner service unavailable"
        )
    
    async def handle_action(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle fitness module actions.

        Note: workout-planner service requires authentication.
        Full integration requires auth token passing.
        """
        # TODO: Implement authentication token passing
        user_id = data.get("user_id", settings.default_user_id)

        if action == "health_check":
            healthy = await self.client.health_check()
            return {"status": "success", "healthy": healthy}

        # Placeholder actions until authentication is integrated
        return {
            "status": "error",
            "message": "Fitness module requires authentication integration to be completed"
        }

    async def get_summary(self) -> ModuleSummary:
        """Get summary information for the fitness module.

        Note: Requires authentication integration for full functionality.
        """
        healthy = await self.client.health_check()

        # Placeholder stats until authentication is integrated
        return ModuleSummary(
            name=self.name,
            enabled=self.is_enabled,
            healthy=healthy,
            stats={
                "service_status": "connected" if healthy else "disconnected",
                "auth_required": True,
            },
            recent_items=[],
            quick_actions=[
                QuickAction(
                    id="health_check",
                    label="Check Service",
                    action="health_check",
                    icon="fitness_center"
                ),
            ],
        )
