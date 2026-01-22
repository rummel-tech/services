"""Entrepreneurship module for Artemis personal OS."""
from typing import Any, Dict
from uuid import uuid4
from artemis.core.module import BaseModule, ModuleConfig, ModuleStatus, ModuleSummary, QuickAction


class EntrepreneurshipModule(BaseModule):
    """Module for managing entrepreneurial endeavors and business activities.
    
    Features:
    - Business idea tracking
    - Venture management
    - Goal and milestone tracking
    - Network and contact management
    """
    
    def __init__(self, config: ModuleConfig) -> None:
        """Initialize the entrepreneurship module."""
        super().__init__(config)
        self.ventures: Dict[str, Any] = {}
        self.ideas: Dict[str, Any] = {}
        self.milestones: Dict[str, Any] = {}
    
    async def initialize(self) -> None:
        """Initialize the entrepreneurship module."""
        self._initialized = True
    
    async def shutdown(self) -> None:
        """Shutdown the entrepreneurship module."""
        self._initialized = False
    
    async def get_status(self) -> ModuleStatus:
        """Get the current status of the entrepreneurship module."""
        return ModuleStatus(
            name=self.name,
            enabled=self.is_enabled,
            healthy=self._initialized,
            message=f"Managing {len(self.ventures)} ventures and {len(self.ideas)} ideas"
        )
    
    async def handle_action(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle entrepreneurship module actions."""
        if action == "create_venture":
            venture_id = data.get("id", f"venture_{uuid4().hex[:8]}")
            self.ventures[venture_id] = data
            return {"status": "success", "venture_id": venture_id}
        
        elif action == "add_idea":
            idea_id = data.get("id", f"idea_{uuid4().hex[:8]}")
            self.ideas[idea_id] = data
            return {"status": "success", "idea_id": idea_id}
        
        elif action == "set_milestone":
            milestone_id = data.get("id", f"milestone_{uuid4().hex[:8]}")
            self.milestones[milestone_id] = data
            return {"status": "success", "milestone_id": milestone_id}
        
        elif action == "list_ventures":
            return {"ventures": list(self.ventures.values())}

        return {"status": "error", "message": f"Unknown action: {action}"}

    async def get_summary(self) -> ModuleSummary:
        """Get summary information for the entrepreneurship module."""
        active_milestones = sum(
            1 for milestone in self.milestones.values()
            if milestone.get("status") == "active"
        )

        recent_ventures = sorted(
            self.ventures.values(),
            key=lambda x: x.get("created_at", ""),
            reverse=True
        )[:3]

        recent_ideas = sorted(
            self.ideas.values(),
            key=lambda x: x.get("created_at", ""),
            reverse=True
        )[:2]

        return ModuleSummary(
            name=self.name,
            enabled=self.is_enabled,
            healthy=self._initialized,
            stats={
                "venture_count": len(self.ventures),
                "idea_count": len(self.ideas),
                "active_milestones": active_milestones,
            },
            recent_items=[
                *[{"type": "venture", **v} for v in recent_ventures],
                *[{"type": "idea", **i} for i in recent_ideas],
            ],
            quick_actions=[
                QuickAction(id="add_idea", label="Capture Idea", action="add_idea", icon="lightbulb"),
                QuickAction(id="create_venture", label="New Venture", action="create_venture", icon="rocket_launch"),
            ],
        )
