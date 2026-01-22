from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date

app = FastAPI(
    title="Meals Planner API",
    version="0.1.0",
    root_path="/meal-planner"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

def _default_weekly_meal_plan(user_id: str):
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


def _day_name_from_date_str(date_str: Optional[str]) -> str:
    if date_str:
        try:
            d = datetime.fromisoformat(date_str).date()
        except Exception:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                # fallback to today if parse fails
                d = date.today()
    else:
        d = date.today()
    return d.strftime("%A")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/ready")
async def ready():
    return {"status": "ready"}

@app.get("/meals/weekly-plan/{user_id}")
async def get_weekly_meal_plan(user_id: str, week_start: Optional[str] = None):
    plan = _default_weekly_meal_plan(user_id)
    if week_start:
        plan["week_start"] = week_start
    return plan


@app.get("/meals/today/{user_id}")
async def get_meal_for_today(user_id: str, date: Optional[str] = None):
    """Return the meals for the provided date (ISO or YYYY-MM-DD). Defaults to today."""
    day_name = _day_name_from_date_str(date)
    plan = _default_weekly_meal_plan(user_id)
    for d in plan.get("days", []):
        if d.get("day") == day_name:
            return {"user_id": user_id, "day": day_name, "meals": d.get("meals", [])}
    # fallback: return an empty day structure
    return {"user_id": user_id, "day": day_name, "meals": []}
