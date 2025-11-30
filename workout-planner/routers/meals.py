from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional, List, Dict
from auth_service import TokenData
from routers.auth import get_current_user
from logging_config import get_logger
import metrics

log = get_logger("api.meals")

router = APIRouter(prefix="/meals", tags=["meals"])


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


def _default_weekly_meal_plan(user_id: str) -> Dict:
    sample = [
        ("Monday", [
            {"name": "Oats + Berries", "calories": 350},
            {"name": "Chicken Salad", "calories": 500},
            {"name": "Salmon + Quinoa + Greens", "calories": 600}
        ]),
        ("Tuesday", [
            {"name": "Greek Yogurt + Granola", "calories": 300},
            {"name": "Turkey Wrap", "calories": 450},
            {"name": "Stir Fry (Tofu/Veg)", "calories": 550}
        ]),
        ("Wednesday", [
            {"name": "Eggs + Toast", "calories": 400},
            {"name": "Buddha Bowl", "calories": 500},
            {"name": "Lean Beef + Sweet Potato", "calories": 650}
        ]),
        ("Thursday", [
            {"name": "Smoothie (Protein)", "calories": 300},
            {"name": "Sushi (Lean) ", "calories": 500},
            {"name": "Pasta + Chicken + Veg", "calories": 650}
        ]),
        ("Friday", [
            {"name": "Avocado Toast", "calories": 350},
            {"name": "Grain Bowl", "calories": 500},
            {"name": "Fish Tacos", "calories": 600}
        ]),
        ("Saturday", [
            {"name": "Pancakes (Protein)", "calories": 450},
            {"name": "Burger (Lean) + Salad", "calories": 700},
            {"name": "Pizza (Thin crust) + Veg", "calories": 700}
        ]),
        ("Sunday", [
            {"name": "Bagel + Eggs", "calories": 500},
            {"name": "Leftovers / Meal Prep", "calories": 600},
            {"name": "Roast Chicken + Veg", "calories": 650}
        ]),
    ]
    days = [{"day": d, "meals": m} for d, m in sample]
    return {
        "user_id": user_id,
        "focus": "balanced",
        "days": days,
    }


@router.get("/health")
def meals_health():
    return {"status": "ok"}


@router.get("/weekly-plan/{user_id}")
def get_weekly_meal_plan(
    user_id: str,
    week_start: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")

    plan = _default_weekly_meal_plan(user_id)
    if week_start:
        plan["week_start"] = week_start
    metrics.record_domain_event("meals_weekly_plan_default")
    log.info("meals_weekly_plan_default", extra={"user_id": user_id, "week_start": plan.get("week_start")})
    return plan


@router.put("/weekly-plan/{user_id}")
def save_weekly_meal_plan(
    user_id: str,
    plan: WeeklyMealPlan,
    current_user: TokenData = Depends(get_current_user),
):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: user mismatch")
    raise HTTPException(status_code=501, detail="Meal plan persistence not implemented yet")
