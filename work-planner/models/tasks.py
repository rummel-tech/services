"""Pydantic models for day planners, tasks, and week planners."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# --- Tasks ---

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = 'medium'    # low | medium | high | urgent
    scheduled_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    plan_id: Optional[str] = None
    pomodoro_block: Optional[int] = None
    task_category: Optional[str] = None  # corporate | farm | appDevelopment (null == corporate)


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    scheduled_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    completed: Optional[bool] = None
    plan_id: Optional[str] = None
    pomodoro_block: Optional[int] = None
    task_category: Optional[str] = None


class Task(BaseModel):
    id: str
    user_id: str
    day_planner_id: str
    title: str
    description: Optional[str] = None
    priority: str
    scheduled_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    completed: bool = False
    plan_id: Optional[str] = None
    pomodoro_block: Optional[int] = None
    task_category: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# --- Day Planner ---

class DayPlannerCreate(BaseModel):
    date: str   # ISO date string e.g. "2026-03-29"
    notes: Optional[str] = None


class DayPlannerUpdate(BaseModel):
    notes: Optional[str] = None


class DayPlanner(BaseModel):
    id: str
    user_id: str
    date: str
    notes: Optional[str] = None
    tasks: List[Task] = []
    created_at: datetime
    updated_at: datetime


# --- Week Planner ---

class WeekPlannerCreate(BaseModel):
    week_start_date: str    # ISO date string for Monday of the week
    weekly_goals: List[str] = []
    notes: Optional[str] = None


class WeekPlannerUpdate(BaseModel):
    weekly_goals: Optional[List[str]] = None
    notes: Optional[str] = None


class WeekPlanner(BaseModel):
    id: str
    user_id: str
    week_start_date: str
    weekly_goals: List[str] = []
    notes: Optional[str] = None
    day_planners: List[DayPlanner] = []
    created_at: datetime
    updated_at: datetime
