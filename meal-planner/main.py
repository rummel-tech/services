"""
Meal Planner API Service
"""

import sys
from pathlib import Path
from typing import Optional, List

from pydantic import BaseModel

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import create_app, ServiceConfig, day_name_from_date

# Service configuration
config = ServiceConfig(
    name="meal-planner",
    title="Meal Planner API",
    version="0.1.0",
    description="Weekly meal planning and nutrition tracking",
    port=8010,
)

app = create_app(config)


# Models
class MealItem(BaseModel):
    name: str
    calories: Optional[int] = None
    protein_g: Optional[int] = None
    carbs_g: Optional[int] = None
    fat_g: Optional[int] = None


class DailyMeals(BaseModel):
    day: str
    meals: List[MealItem]


class WeeklyMealPlan(BaseModel):
    user_id: str
    week_start: Optional[str] = None
    focus: Optional[str] = "balanced"
    days: List[DailyMeals]


# Mock data
def _default_weekly_meal_plan(user_id: str) -> dict:
    days = [
        {"day": "Monday", "meals": [
            {"name": "Oats + Berries", "calories": 350},
            {"name": "Chicken Salad", "calories": 500},
            {"name": "Salmon + Quinoa + Greens", "calories": 600},
        ]},
        {"day": "Tuesday", "meals": [
            {"name": "Greek Yogurt + Granola", "calories": 300},
            {"name": "Turkey Wrap", "calories": 450},
            {"name": "Stir Fry (Tofu/Veg)", "calories": 550},
        ]},
        {"day": "Wednesday", "meals": [
            {"name": "Smoothie Bowl", "calories": 320},
            {"name": "Quinoa Salad", "calories": 480},
            {"name": "Chicken + Sweet Potato", "calories": 620},
        ]},
        {"day": "Thursday", "meals": [
            {"name": "Avocado Toast + Eggs", "calories": 400},
            {"name": "Sushi Bowl", "calories": 500},
            {"name": "Lentil Curry + Rice", "calories": 580},
        ]},
        {"day": "Friday", "meals": [
            {"name": "Protein Pancakes", "calories": 370},
            {"name": "Grilled Chicken + Veggies", "calories": 520},
            {"name": "Pasta with Pesto", "calories": 650},
        ]},
        {"day": "Saturday", "meals": [
            {"name": "Breakfast Burrito", "calories": 450},
            {"name": "Caesar Salad with Shrimp", "calories": 540},
            {"name": "Homemade Pizza (Veg)", "calories": 700},
        ]},
        {"day": "Sunday", "meals": [
            {"name": "French Toast", "calories": 420},
            {"name": "Roast Beef + Potatoes", "calories": 700},
            {"name": "Vegetable Soup + Bread", "calories": 480},
        ]},
    ]
    return {"user_id": user_id, "focus": "balanced", "days": days}


# Endpoints
@app.get("/meals/weekly-plan/{user_id}", tags=["Meals"])
async def get_weekly_meal_plan(user_id: str, week_start: Optional[str] = None):
    """Get the weekly meal plan for a user."""
    plan = _default_weekly_meal_plan(user_id)
    if week_start:
        plan["week_start"] = week_start
    return plan


@app.get("/meals/today/{user_id}", tags=["Meals"])
async def get_meal_for_today(user_id: str, date: Optional[str] = None):
    """Get meals for today (or specified date)."""
    day_name = day_name_from_date(date)
    plan = _default_weekly_meal_plan(user_id)

    for d in plan.get("days", []):
        if d.get("day") == day_name:
            total_calories = sum(m.get("calories", 0) for m in d.get("meals", []))
            return {
                "user_id": user_id,
                "day": day_name,
                "meals": d.get("meals", []),
                "total_calories": total_calories,
            }

    return {"user_id": user_id, "day": day_name, "meals": [], "total_calories": 0}
