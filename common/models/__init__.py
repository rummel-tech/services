"""
Common data models shared across all services.

These models provide a consistent foundation for entities across the platform.
"""

from .base import (
    BaseEntity,
    UserOwnedEntity,
    Task,
    Goal,
    Asset,
    MaintenanceRecord,
    TaskStatus,
    Priority,
    AssetCondition,
    TaskCreate,
    TaskUpdate,
    GoalCreate,
    GoalUpdate,
    AssetCreate,
    AssetUpdate,
    MaintenanceRecordCreate,
    MaintenanceRecordUpdate,
)

__all__ = [
    "BaseEntity",
    "UserOwnedEntity",
    "Task",
    "Goal",
    "Asset",
    "MaintenanceRecord",
    "TaskStatus",
    "Priority",
    "AssetCondition",
    "TaskCreate",
    "TaskUpdate",
    "GoalCreate",
    "GoalUpdate",
    "AssetCreate",
    "AssetUpdate",
    "MaintenanceRecordCreate",
    "MaintenanceRecordUpdate",
]
