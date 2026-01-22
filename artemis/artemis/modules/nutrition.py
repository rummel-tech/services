"""Nutrition management module for Artemis personal OS."""
from datetime import date
from typing import Any, Dict
from artemis.core.module import BaseModule, ModuleConfig, ModuleStatus, ModuleSummary, QuickAction
from artemis.core.client import ServiceClient
from artemis.core.settings import settings


class NutritionModule(BaseModule):
    """Module for managing nutrition, meal planning, and dietary tracking.

    Proxies requests to the meal-planner backend service.

    Features:
    - Meal logging
    - Nutrition tracking
    - Diet goal management
    - Recipe storage
    """

    def __init__(self, config: ModuleConfig) -> None:
        """Initialize the nutrition module."""
        super().__init__(config)
        self.client = ServiceClient(settings.services.meal_planner_url)

    async def initialize(self) -> None:
        """Initialize the nutrition module."""
        # Check backend service health
        self._initialized = await self.client.health_check()

    async def shutdown(self) -> None:
        """Shutdown the nutrition module."""
        await self.client.close()
        self._initialized = False
    
    async def get_status(self) -> ModuleStatus:
        """Get the current status of the nutrition module."""
        healthy = await self.client.health_check()
        user_id = settings.default_user_id

        try:
            meals = await self.client.get(f"/meals/{user_id}")
            meal_count = len(meals) if isinstance(meals, list) else 0
        except:
            meal_count = 0

        return ModuleStatus(
            name=self.name,
            enabled=self.is_enabled,
            healthy=healthy,
            message=f"Tracking {meal_count} meals (via meal-planner service)"
        )
    
    async def handle_action(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle nutrition module actions."""
        user_id = data.get("user_id", settings.default_user_id)

        if action == "log_meal":
            # Create meal via meal-planner API
            meal_data = {
                "user_id": user_id,
                "name": data.get("name", "Meal"),
                "meal_type": data.get("meal_type", "snack"),
                "date": data.get("date", str(date.today())),
                "calories": data.get("calories"),
                "protein_g": data.get("protein_g"),
                "carbs_g": data.get("carbs_g"),
                "fat_g": data.get("fat_g"),
                "notes": data.get("notes"),
            }
            result = await self.client.post("/meals", json=meal_data)
            return {"status": "success", "meal": result}

        elif action == "list_meals":
            # List meals for user
            meals = await self.client.get(f"/meals/{user_id}")
            return {"meals": meals}

        elif action == "get_today":
            # Get today's meals
            result = await self.client.get(f"/meals/today/{user_id}")
            return {"daily_meals": result}

        elif action == "get_weekly_plan":
            # Get weekly meal plan
            result = await self.client.get(f"/meals/weekly-plan/{user_id}")
            return {"weekly_plan": result}

        return {"status": "error", "message": f"Unknown action: {action}"}

    async def get_summary(self) -> ModuleSummary:
        """Get summary information for the nutrition module."""
        user_id = settings.default_user_id
        healthy = await self.client.health_check()

        try:
            # Get today's meals from backend
            daily_data = await self.client.get(f"/meals/today/{user_id}")
            meals_today = len(daily_data.get("meals", []))
            total_calories = daily_data.get("total_calories", 0)

            # Get all meals to count total
            all_meals = await self.client.get(f"/meals/{user_id}")
            total_meals = len(all_meals) if isinstance(all_meals, list) else 0

            # Recent meals (up to 5)
            recent_meals = all_meals[:5] if isinstance(all_meals, list) else []

        except:
            meals_today = 0
            total_calories = 0
            total_meals = 0
            recent_meals = []

        return ModuleSummary(
            name=self.name,
            enabled=self.is_enabled,
            healthy=healthy,
            stats={
                "meals_today": meals_today,
                "total_calories": total_calories,
                "total_meals": total_meals,
            },
            recent_items=[{"type": "meal", **m} for m in recent_meals],
            quick_actions=[
                QuickAction(id="log_meal", label="Log Meal", action="log_meal", icon="restaurant"),
                QuickAction(id="get_today", label="Today's Meals", action="get_today", icon="today"),
            ],
        )
