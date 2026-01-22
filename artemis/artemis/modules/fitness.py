"""Fitness tracking module for Artemis personal OS."""
from datetime import date, timedelta
from typing import Any, Dict
from uuid import uuid4
from artemis.core.module import BaseModule, ModuleConfig, ModuleStatus, ModuleSummary, QuickAction


class FitnessModule(BaseModule):
    """Module for tracking fitness activities and health metrics.
    
    Features:
    - Workout logging
    - Exercise tracking
    - Fitness goal setting
    - Progress monitoring
    """
    
    def __init__(self, config: ModuleConfig) -> None:
        """Initialize the fitness module."""
        super().__init__(config)
        self.workouts: Dict[str, Any] = {}
        self.goals: Dict[str, Any] = {}
    
    async def initialize(self) -> None:
        """Initialize the fitness module."""
        self._initialized = True
    
    async def shutdown(self) -> None:
        """Shutdown the fitness module."""
        self._initialized = False
    
    async def get_status(self) -> ModuleStatus:
        """Get the current status of the fitness module."""
        return ModuleStatus(
            name=self.name,
            enabled=self.is_enabled,
            healthy=self._initialized,
            message=f"Tracking {len(self.workouts)} workouts and {len(self.goals)} fitness goals"
        )
    
    async def handle_action(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle fitness module actions."""
        if action == "log_workout":
            workout_id = data.get("id", f"workout_{uuid4().hex[:8]}")
            self.workouts[workout_id] = data
            return {"status": "success", "workout_id": workout_id}
        
        elif action == "set_goal":
            goal_id = data.get("id", f"goal_{uuid4().hex[:8]}")
            self.goals[goal_id] = data
            return {"status": "success", "goal_id": goal_id}
        
        elif action == "list_workouts":
            return {"workouts": list(self.workouts.values())}
        
        elif action == "list_goals":
            return {"goals": list(self.goals.values())}

        return {"status": "error", "message": f"Unknown action: {action}"}

    async def get_summary(self) -> ModuleSummary:
        """Get summary information for the fitness module."""
        today = date.today()
        week_ago = (today - timedelta(days=7)).isoformat()

        workouts_this_week = sum(
            1 for workout in self.workouts.values()
            if workout.get("date", "") >= week_ago
        )

        active_goals = sum(
            1 for goal in self.goals.values()
            if goal.get("status") == "active"
        )

        recent_workouts = sorted(
            self.workouts.values(),
            key=lambda x: x.get("date", ""),
            reverse=True
        )[:5]

        return ModuleSummary(
            name=self.name,
            enabled=self.is_enabled,
            healthy=self._initialized,
            stats={
                "workouts_this_week": workouts_this_week,
                "total_workouts": len(self.workouts),
                "active_goals": active_goals,
            },
            recent_items=[{"type": "workout", **w} for w in recent_workouts],
            quick_actions=[
                QuickAction(id="log_workout", label="Log Workout", action="log_workout", icon="fitness_center"),
                QuickAction(id="set_goal", label="Set Goal", action="set_goal", icon="flag"),
            ],
        )
