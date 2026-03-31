"""Pydantic models for weekly plans and activities."""

from typing import Optional, List
from pydantic import BaseModel


class ActivityCreate(BaseModel):
    title: str
    description: Optional[str] = None
    goal_id: Optional[str] = None
    duration_minutes: int
    scheduled_time: str  # ISO 8601

    class Config:
        str_strip_whitespace = True


class ActivityUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    scheduled_time: Optional[str] = None
    is_completed: Optional[bool] = None
    actual_minutes: Optional[int] = None


class Activity(BaseModel):
    id: str
    plan_id: str
    goal_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    duration_minutes: int
    actual_minutes: Optional[int] = None
    scheduled_time: str
    is_completed: bool
    completed_at: Optional[str] = None
    created_at: str
    updated_at: str


class PlanCreate(BaseModel):
    title: str
    week_start_date: str  # ISO date — will be normalized to Monday

    class Config:
        str_strip_whitespace = True


class Plan(BaseModel):
    id: str
    user_id: str
    title: str
    week_start_date: str
    week_end_date: str
    activities: List[Activity] = []
    total_planned_minutes: int = 0
    completion_percentage: float = 0.0
    created_at: str
    updated_at: str
