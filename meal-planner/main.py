"""
Meal Planner API - Nutrition and meal planning service.

Refactored to use database persistence for meal tracking.
"""

import sys
from pathlib import Path
from typing import List, Optional
from uuid import UUID
from datetime import date, datetime

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from common.database import (
    get_connection, get_cursor, dict_from_row,
    init_db, close_db, adapt_query, is_sqlite, get_database_url
)
from routers import artemis as artemis_router

# Initialize FastAPI app
app = FastAPI(
    title="Meal Planner API",
    version="2.0.0",
    description="Nutrition and meal planning service with database persistence",
    root_path="/meal-planner"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(artemis_router.router)

# Check if using SQLite for query adaptation
USE_SQLITE = is_sqlite(get_database_url())


# Models
class MealItem(BaseModel):
    """Individual meal item."""
    id: UUID
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
    """Request model for creating meals."""
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
    """Daily meal summary."""
    date: date
    meals: List[MealItem]
    total_calories: int
    total_protein: int
    total_carbs: int
    total_fat: int


# Startup/shutdown events
@app.on_event("startup")
async def startup():
    """Initialize database connection pool."""
    init_db()


@app.on_event("shutdown")
async def shutdown():
    """Close database connection pool."""
    close_db()


# ============================================================================
# Health Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "meal-planner"}


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    return {"status": "ready", "database": get_database_url()}


# ============================================================================
# Meal Endpoints
# ============================================================================

@app.get("/meals/{user_id}", response_model=List[MealItem])
async def list_meals(user_id: str, start_date: Optional[date] = None, end_date: Optional[date] = None):
    """List meals for a user, optionally filtered by date range."""
    with get_connection() as conn:
        cur = get_cursor(conn)

        if start_date and end_date:
            query = adapt_query(
                "SELECT * FROM meals WHERE user_id = %s AND date BETWEEN %s AND %s ORDER BY date DESC, meal_type",
                USE_SQLITE
            )
            cur.execute(query, (user_id, start_date, end_date))
        else:
            query = adapt_query(
                "SELECT * FROM meals WHERE user_id = %s ORDER BY date DESC, meal_type",
                USE_SQLITE
            )
            cur.execute(query, (user_id,))

        rows = cur.fetchall()
        return [MealItem(**dict_from_row(row, USE_SQLITE)) for row in rows]


@app.post("/meals", response_model=MealItem, status_code=status.HTTP_201_CREATED)
async def create_meal(meal: MealItemCreate):
    """Create a new meal entry."""
    with get_connection() as conn:
        cur = get_cursor(conn)

        if USE_SQLITE:
            import uuid
            meal_id = str(uuid.uuid4())
            query = """INSERT INTO meals (id, user_id, name, meal_type, date, calories, protein_g, carbs_g, fat_g, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            cur.execute(query, (
                meal_id, meal.user_id, meal.name, meal.meal_type, meal.date,
                meal.calories, meal.protein_g, meal.carbs_g, meal.fat_g, meal.notes
            ))
            cur.execute("SELECT * FROM meals WHERE id = ?", (meal_id,))
        else:
            query = """INSERT INTO meals (id, user_id, name, meal_type, date, calories, protein_g, carbs_g, fat_g, notes)
                       VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING *"""
            cur.execute(query, (
                meal.user_id, meal.name, meal.meal_type, meal.date,
                meal.calories, meal.protein_g, meal.carbs_g, meal.fat_g, meal.notes
            ))

        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create meal")
        return MealItem(**dict_from_row(row, USE_SQLITE))


@app.get("/meals/today/{user_id}", response_model=DailyMeals)
async def get_todays_meals(user_id: str, meal_date: Optional[date] = None):
    """Get all meals for today (or specified date)."""
    target_date = meal_date or date.today()

    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query(
            "SELECT * FROM meals WHERE user_id = %s AND date = %s ORDER BY meal_type",
            USE_SQLITE
        )
        cur.execute(query, (user_id, target_date))
        rows = cur.fetchall()
        meals = [MealItem(**dict_from_row(row, USE_SQLITE)) for row in rows]

        # Calculate totals
        total_calories = sum(m.calories or 0 for m in meals)
        total_protein = sum(m.protein_g or 0 for m in meals)
        total_carbs = sum(m.carbs_g or 0 for m in meals)
        total_fat = sum(m.fat_g or 0 for m in meals)

        return DailyMeals(
            date=target_date,
            meals=meals,
            total_calories=total_calories,
            total_protein=total_protein,
            total_carbs=total_carbs,
            total_fat=total_fat
        )


@app.get("/meals/weekly-plan/{user_id}")
async def get_weekly_meal_plan(user_id: str, week_start: Optional[date] = None):
    """Get meal plan for the week."""
    target_week = week_start or date.today()

    # Get 7 days of meals
    from datetime import timedelta
    daily_plans = []

    for day_offset in range(7):
        day = target_week + timedelta(days=day_offset)
        day_meals = await get_todays_meals(user_id, day)
        daily_plans.append({
            "day": day.strftime("%A"),
            "date": day.isoformat(),
            "meals": [meal.dict() for meal in day_meals.meals],
            "total_calories": day_meals.total_calories
        })

    return {
        "user_id": user_id,
        "week_start": target_week.isoformat(),
        "focus": "balanced",
        "days": daily_plans
    }


@app.delete("/meals/{user_id}/{meal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meal(user_id: str, meal_id: UUID):
    """Delete a meal entry."""
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query("DELETE FROM meals WHERE id = %s AND user_id = %s", USE_SQLITE)
        cur.execute(query, (str(meal_id), user_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Meal not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
