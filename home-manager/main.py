from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date

app = FastAPI(title="Home Manager API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class Task(BaseModel):
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    day: str
    category: str
    priority: Optional[str] = "medium"
    completed: bool = False
    estimated_minutes: Optional[int] = None

class Goal(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    category: str
    target_date: Optional[str] = None
    progress: Optional[int] = 0
    is_active: bool = True

class WeeklyTasks(BaseModel):
    user_id: str
    week_start: Optional[str] = None
    tasks: List[Task]

class DailyTasks(BaseModel):
    user_id: str
    day: str
    tasks: List[Task]

# Default data
def _default_weekly_tasks(user_id: str):
    tasks = [
        {"id": "1", "title": "Laundry", "day": "Monday", "category": "chores", "priority": "high", "completed": False, "estimated_minutes": 60},
        {"id": "2", "title": "Grocery Shopping", "day": "Monday", "category": "errands", "priority": "high", "completed": False, "estimated_minutes": 90},
        {"id": "3", "title": "Vacuum Living Room", "day": "Tuesday", "category": "cleaning", "priority": "medium", "completed": False, "estimated_minutes": 30},
        {"id": "4", "title": "Water Plants", "day": "Tuesday", "category": "maintenance", "priority": "low", "completed": False, "estimated_minutes": 15},
        {"id": "5", "title": "Clean Bathrooms", "day": "Wednesday", "category": "cleaning", "priority": "high", "completed": False, "estimated_minutes": 45},
        {"id": "6", "title": "Meal Prep", "day": "Wednesday", "category": "cooking", "priority": "medium", "completed": False, "estimated_minutes": 120},
        {"id": "7", "title": "Take Out Trash", "day": "Thursday", "category": "chores", "priority": "high", "completed": False, "estimated_minutes": 10},
        {"id": "8", "title": "Organize Pantry", "day": "Thursday", "category": "organizing", "priority": "low", "completed": False, "estimated_minutes": 60},
        {"id": "9", "title": "Mow Lawn", "day": "Friday", "category": "outdoor", "priority": "medium", "completed": False, "estimated_minutes": 90},
        {"id": "10", "title": "Clean Kitchen", "day": "Friday", "category": "cleaning", "priority": "high", "completed": False, "estimated_minutes": 40},
        {"id": "11", "title": "Change Bed Sheets", "day": "Saturday", "category": "chores", "priority": "medium", "completed": False, "estimated_minutes": 20},
        {"id": "12", "title": "Deep Clean Fridge", "day": "Saturday", "category": "cleaning", "priority": "low", "completed": False, "estimated_minutes": 45},
        {"id": "13", "title": "Vacuum Bedrooms", "day": "Sunday", "category": "cleaning", "priority": "medium", "completed": False, "estimated_minutes": 30},
        {"id": "14", "title": "Plan Next Week", "day": "Sunday", "category": "planning", "priority": "high", "completed": False, "estimated_minutes": 30},
    ]
    return {"user_id": user_id, "tasks": tasks}

def _default_goals(user_id: str):
    goals = [
        {
            "id": "g1",
            "title": "Organize Garage",
            "description": "Sort through items, donate unused things, create storage system",
            "category": "organizing",
            "target_date": "2025-12-31",
            "progress": 25,
            "is_active": True
        },
        {
            "id": "g2",
            "title": "Deep Clean All Rooms",
            "description": "Complete deep clean of every room in the house",
            "category": "cleaning",
            "target_date": "2025-12-15",
            "progress": 40,
            "is_active": True
        },
        {
            "id": "g3",
            "title": "Create Meal Planning System",
            "description": "Establish regular meal planning and prep routine",
            "category": "cooking",
            "target_date": "2025-11-30",
            "progress": 60,
            "is_active": True
        },
    ]
    return goals

def _day_name_from_date_str(date_str: Optional[str]) -> str:
    if date_str:
        try:
            d = datetime.fromisoformat(date_str).date()
        except Exception:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                d = date.today()
    else:
        d = date.today()
    return d.strftime("%A")

# Endpoints
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/ready")
async def ready():
    return {"status": "ready"}

@app.get("/tasks/weekly/{user_id}")
async def get_weekly_tasks(user_id: str, week_start: Optional[str] = None):
    """Get all tasks for the week"""
    data = _default_weekly_tasks(user_id)
    if week_start:
        data["week_start"] = week_start
    return data

@app.get("/tasks/today/{user_id}")
async def get_today_tasks(user_id: str, date: Optional[str] = None):
    """Get tasks for today (or specified date)"""
    day_name = _day_name_from_date_str(date)
    all_tasks = _default_weekly_tasks(user_id)

    today_tasks = [task for task in all_tasks["tasks"] if task.get("day") == day_name]
    return {"user_id": user_id, "day": day_name, "tasks": today_tasks}

@app.get("/tasks/category/{user_id}/{category}")
async def get_tasks_by_category(user_id: str, category: str):
    """Get all tasks in a specific category"""
    all_tasks = _default_weekly_tasks(user_id)
    filtered = [task for task in all_tasks["tasks"] if task.get("category") == category]
    return {"user_id": user_id, "category": category, "tasks": filtered}

@app.get("/goals/{user_id}")
async def get_goals(user_id: str):
    """Get all goals for user"""
    goals = _default_goals(user_id)
    return {"user_id": user_id, "goals": goals}

@app.get("/stats/{user_id}")
async def get_stats(user_id: str):
    """Get statistics for user"""
    all_tasks = _default_weekly_tasks(user_id)
    total_tasks = len(all_tasks["tasks"])
    completed_tasks = sum(1 for t in all_tasks["tasks"] if t.get("completed", False))
    total_minutes = sum(t.get("estimated_minutes", 0) for t in all_tasks["tasks"])

    goals = _default_goals(user_id)
    active_goals = sum(1 for g in goals if g.get("is_active", True))
    avg_progress = sum(g.get("progress", 0) for g in goals) / len(goals) if goals else 0

    return {
        "user_id": user_id,
        "tasks": {
            "total": total_tasks,
            "completed": completed_tasks,
            "completion_rate": round(completed_tasks / total_tasks * 100, 1) if total_tasks > 0 else 0,
            "total_estimated_minutes": total_minutes
        },
        "goals": {
            "total": len(goals),
            "active": active_goals,
            "average_progress": round(avg_progress, 1)
        }
    }
