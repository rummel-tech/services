"""
Meal Planner API - Nutrition and meal planning service.
"""

import logging
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _load_env() -> None:
    import os
    try:
        load_dotenv(override=False)
        custom_path = os.environ.get("SECRETS_ENV_PATH")
        if custom_path:
            secrets_env = Path(custom_path)
        else:
            repo_root = Path(__file__).resolve().parents[2]
            secrets_env = repo_root / "config" / "secrets" / "local.env"
        if secrets_env.exists():
            load_dotenv(dotenv_path=secrets_env, override=True)
    except Exception:
        pass


_load_env()

from common.aws_secrets import inject_secrets_from_aws
inject_secrets_from_aws()

from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel

from common import create_app, ServiceConfig
from common.database import (
    get_connection, get_cursor, dict_from_row,
    init_db, close_db, adapt_query, is_sqlite, get_database_url,
)
from core.settings import get_settings
from routers import artemis as artemis_router
from routers.auth import TokenData, require_token

logger = logging.getLogger(__name__)

settings = get_settings()

config = ServiceConfig(
    name="meal-planner",
    title="Meal Planner API",
    version="2.0.0",
    description="Nutrition and meal planning service with database persistence",
    port=settings.port,
    environment=settings.environment,
    debug=settings.debug,
    log_level=settings.log_level,
    cors_origins=settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins],
    enable_security_headers=True,
    enable_request_logging=True,
    enable_error_handlers=True,
    enable_metrics=True,
    enable_rate_limiting=(settings.environment == "production"),
    redis_enabled=settings.redis_enabled,
    redis_url=settings.redis_url,
    on_startup=[init_db],
    on_shutdown=[close_db],
)

app = create_app(config)
app.include_router(artemis_router.router)

USE_SQLITE = is_sqlite(get_database_url())


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class MealItem(BaseModel):
    id: uuid.UUID
    user_id: str
    name: str
    meal_type: str  # breakfast, lunch, dinner, snack
    date: date
    calories: Optional[int] = None
    protein_g: Optional[int] = None
    carbs_g: Optional[int] = None
    fat_g: Optional[int] = None
    notes: Optional[str] = None


class MealItemCreate(BaseModel):
    user_id: str
    name: str
    meal_type: str
    date: date
    calories: Optional[int] = None
    protein_g: Optional[int] = None
    carbs_g: Optional[int] = None
    fat_g: Optional[int] = None
    notes: Optional[str] = None


class DailyMeals(BaseModel):
    user_id: str
    date: date
    day: str
    meals: List[MealItem]
    total_calories: int
    total_protein: int
    total_carbs: int
    total_fat: int


# ---------------------------------------------------------------------------
# Meal endpoints
# ---------------------------------------------------------------------------

@app.get("/meals/{user_id}", response_model=List[MealItem])
async def list_meals(
    user_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    token: TokenData = Depends(require_token),
):
    with get_connection() as conn:
        cur = get_cursor(conn)
        if start_date and end_date:
            query = adapt_query(
                "SELECT * FROM meals WHERE user_id = %s AND date BETWEEN %s AND %s ORDER BY date DESC, meal_type",
                USE_SQLITE,
            )
            cur.execute(query, (user_id, start_date, end_date))
        else:
            query = adapt_query(
                "SELECT * FROM meals WHERE user_id = %s ORDER BY date DESC, meal_type",
                USE_SQLITE,
            )
            cur.execute(query, (user_id,))
        rows = cur.fetchall()
        return [MealItem(**dict_from_row(row, USE_SQLITE)) for row in rows]


@app.post("/meals", response_model=MealItem, status_code=status.HTTP_201_CREATED)
async def create_meal(meal: MealItemCreate, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        cur = get_cursor(conn)
        if USE_SQLITE:
            meal_id = str(uuid.uuid4())
            query = """INSERT INTO meals (id, user_id, name, meal_type, date, calories, protein_g, carbs_g, fat_g, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            cur.execute(query, (
                meal_id, meal.user_id, meal.name, meal.meal_type, meal.date,
                meal.calories, meal.protein_g, meal.carbs_g, meal.fat_g, meal.notes,
            ))
            cur.execute("SELECT * FROM meals WHERE id = ?", (meal_id,))
        else:
            query = """INSERT INTO meals (id, user_id, name, meal_type, date, calories, protein_g, carbs_g, fat_g, notes)
                       VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING *"""
            cur.execute(query, (
                meal.user_id, meal.name, meal.meal_type, meal.date,
                meal.calories, meal.protein_g, meal.carbs_g, meal.fat_g, meal.notes,
            ))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create meal")
        logger.info("Created meal '%s' for user %s", meal.name, meal.user_id)
        return MealItem(**dict_from_row(row, USE_SQLITE))


@app.get("/meals/today/{user_id}", response_model=DailyMeals)
async def get_todays_meals(
    user_id: str,
    meal_date: Optional[date] = Query(None, alias="date"),
    token: TokenData = Depends(require_token),
):
    target_date = meal_date or date.today()
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query(
            "SELECT * FROM meals WHERE user_id = %s AND date = %s ORDER BY meal_type",
            USE_SQLITE,
        )
        cur.execute(query, (user_id, target_date.isoformat()))
        rows = cur.fetchall()
        meals = [MealItem(**dict_from_row(row, USE_SQLITE)) for row in rows]
        return DailyMeals(
            user_id=user_id,
            date=target_date,
            day=target_date.strftime("%A"),
            meals=meals,
            total_calories=sum(m.calories or 0 for m in meals),
            total_protein=sum(m.protein_g or 0 for m in meals),
            total_carbs=sum(m.carbs_g or 0 for m in meals),
            total_fat=sum(m.fat_g or 0 for m in meals),
        )


@app.get("/meals/weekly-plan/{user_id}")
async def get_weekly_meal_plan(
    user_id: str,
    week_start: Optional[date] = None,
    token: TokenData = Depends(require_token),
):
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

    daily_plans = []
    for day_offset in range(7):
        day = week_start + timedelta(days=day_offset)
        day_meals = await get_todays_meals(user_id, day, token=token)
        daily_plans.append({
            "day": day.strftime("%A"),
            "date": day.isoformat(),
            "meals": [meal.model_dump(mode="json") for meal in day_meals.meals],
            "total_calories": day_meals.total_calories,
        })

    return {
        "user_id": user_id,
        "week_start": week_start.isoformat(),
        "focus": "balanced",
        "days": daily_plans,
    }


@app.delete("/meals/{user_id}/{meal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meal(user_id: str, meal_id: uuid.UUID, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query("DELETE FROM meals WHERE id = %s AND user_id = %s", USE_SQLITE)
        cur.execute(query, (str(meal_id), user_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Meal not found")
        logger.info("Deleted meal %s for user %s", meal_id, user_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
