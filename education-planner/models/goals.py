"""Pydantic models for education goals."""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel


VALID_CATEGORIES = ('professional', 'personal', 'hobby', 'academic')


class GoalCreate(BaseModel):
    title: str
    description: str = ''
    category: str = 'personal'
    target_date: Optional[str] = None

    class Config:
        str_strip_whitespace = True


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    target_date: Optional[str] = None
    is_completed: Optional[bool] = None


class Goal(BaseModel):
    id: str
    user_id: str
    title: str
    description: str
    category: str
    target_date: Optional[str] = None
    is_completed: bool
    completed_at: Optional[str] = None
    created_at: str
    updated_at: str
