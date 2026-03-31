"""
Meal Planner API - Nutrition and meal planning service.

Refactored to use database persistence for meal tracking.
"""

import logging
import sys
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from common.database import (
    get_connection, get_cursor, dict_from_row,
    init_db, close_db, adapt_query, is_sqlite, get_database_url
)
from routers import artemis as artemis_router
from routers.auth import TokenData, require_token

from contextlib import asynccontextmanager

import os

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting meal-planner API (db=%s)", get_database_url())
    init_db()
    yield
    logger.info("Shutting down meal-planner API")
    close_db()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Meal Planner API",
    version="2.0.0",
    description="Nutrition and meal planning service with database persistence",
    root_path="/meal-planner",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class ProductionMiddleware(BaseHTTPMiddleware):
    """Adds request ID, response time, and security headers to every response."""

    async def dispatch(self, request, call_next):
        request_id = str(uuid.uuid4())
        start = time.monotonic()

        response = await call_next(request)

        elapsed_ms = (time.monotonic() - start) * 1000
        response.headers["x-request-id"] = request_id
        response.headers["x-response-time-ms"] = f"{elapsed_ms:.1f}"
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["x-xss-protection"] = "1; mode=block"
        response.headers["referrer-policy"] = "strict-origin-when-cross-origin"
        return response


allowed_origins = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ProductionMiddleware)

app.include_router(artemis_router.router)

# Check if using SQLite for query adaptation
USE_SQLITE = is_sqlite(get_database_url())


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    logger.warning("HTTP %s %s → %d", request.method, request.url.path, exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "path": request.url.path,
            "method": request.method,
            "status_code": exc.status_code,
            "correlation_id": str(uuid.uuid4()),
            "error": {
                "type": "http_exception",
                "detail": exc.detail,
            },
        },
    )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class MealItem(BaseModel):
    """Individual meal item."""
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
    user_id: str
    date: date
    day: str
    meals: List[MealItem]
    total_calories: int
    total_protein: int
    total_carbs: int
    total_fat: int


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------
@app.get("/")
async def root():
    """Service information."""
    return {
        "service": "meal-planner",
        "status": "operational",
        "version": "2.0.0",
        "endpoints": [
            "/health",
            "/ready",
            "/meals/{user_id}",
            "/meals/today/{user_id}",
            "/meals/weekly-plan/{user_id}",
            "/artemis/manifest",
        ],
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "meal-planner"}


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    return {"status": "ready", "service": "meal-planner"}


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
    """List meals for a user, optionally filtered by date range."""
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
    """Create a new meal entry."""
    with get_connection() as conn:
        cur = get_cursor(conn)

        if USE_SQLITE:
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
        logger.info("Created meal '%s' for user %s", meal.name, meal.user_id)
        return MealItem(**dict_from_row(row, USE_SQLITE))


@app.get("/meals/today/{user_id}", response_model=DailyMeals)
async def get_todays_meals(
    user_id: str,
    meal_date: Optional[date] = Query(None, alias="date"),
    token: TokenData = Depends(require_token),
):
    """Get all meals for today (or specified date)."""
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
    """Get meal plan for the week (defaults to Monday of current week)."""
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # Monday

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
    """Delete a meal entry."""
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query("DELETE FROM meals WHERE id = %s AND user_id = %s", USE_SQLITE)
        cur.execute(query, (str(meal_id), user_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Meal not found")
        logger.info("Deleted meal %s for user %s", meal_id, user_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
