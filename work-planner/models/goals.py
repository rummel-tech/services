"""Pydantic models for goals."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class GoalCreate(BaseModel):
    title: str
    description: Optional[str] = None
    goal_type: str = 'corporate'   # corporate | farm | appDevelopment | homeAuto
    status: str = 'notStarted'     # notStarted | inProgress | completed | abandoned
    target_date: Optional[str] = None


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    goal_type: Optional[str] = None
    status: Optional[str] = None
    target_date: Optional[str] = None


class Goal(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str] = None
    goal_type: str
    status: str
    target_date: Optional[str] = None
    created_at: datetime
    updated_at: datetime
