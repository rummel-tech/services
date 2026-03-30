"""Pydantic models for plans."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class PlanCreate(BaseModel):
    goal_id: str
    title: str
    description: Optional[str] = None
    status: str = 'draft'     # draft | active | completed | cancelled
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    steps: List[str] = []


class PlanUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    steps: Optional[List[str]] = None


class Plan(BaseModel):
    id: str
    user_id: str
    goal_id: str
    title: str
    description: Optional[str] = None
    status: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    steps: List[str] = []
    created_at: datetime
    updated_at: datetime
