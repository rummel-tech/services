"""
Base models for all services.

These models provide consistent structure and behavior across the platform.
All entities should inherit from BaseEntity or UserOwnedEntity.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class TaskStatus(str, Enum):
    """Standard task statuses across all services.

    Artemis contract (and preferred values): open, in_progress, done.
    Legacy values kept for backward compatibility with existing data.
    """
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    # Legacy — backward compat
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"


class Priority(str, Enum):
    """Standard priority levels across all services."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AssetCondition(str, Enum):
    """Standard asset condition ratings."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    NEEDS_REPAIR = "needs_repair"


class BaseEntity(BaseModel):
    """
    Base model for all entities in the system.

    Provides:
    - UUID-based IDs
    - Automatic timestamps
    - Consistent serialization
    """
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        }
    )

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def dict(self, *args, **kwargs):
        """Override dict to convert UUIDs and datetimes to strings."""
        d = super().model_dump(*args, **kwargs)
        if 'id' in d and isinstance(d['id'], UUID):
            d['id'] = str(d['id'])
        if 'created_at' in d and isinstance(d['created_at'], datetime):
            d['created_at'] = d['created_at'].isoformat()
        if 'updated_at' in d and isinstance(d['updated_at'], datetime):
            d['updated_at'] = d['updated_at'].isoformat()
        return d


class UserOwnedEntity(BaseEntity):
    """
    Base for entities owned by users.

    Ensures multi-tenancy and user isolation.
    """
    user_id: str


class Task(UserOwnedEntity):
    """
    Shared task model across all services.

    Used by:
    - home-manager (household tasks)
    - workout-planner (workout tasks)
    - Any service needing task tracking
    """
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.OPEN
    priority: Priority = Priority.MEDIUM
    category: str
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_minutes: Optional[int] = None
    tags: list[str] = Field(default_factory=list)

    # Service-specific context
    context: dict = Field(default_factory=dict)  # For service-specific data


class Goal(UserOwnedEntity):
    """
    Shared goal model across all services.

    Used by:
    - workout-planner (fitness goals)
    - home-manager (home improvement goals)
    - finance module (financial goals)
    - Any service with goal tracking
    """
    title: str
    description: Optional[str] = None
    category: str
    target_value: Optional[float] = None
    target_unit: Optional[str] = None
    target_date: Optional[datetime] = None
    current_value: Optional[float] = None
    is_active: bool = True
    progress_percentage: int = Field(default=0, ge=0, le=100)
    notes: Optional[str] = None

    # Service-specific context
    context: dict = Field(default_factory=dict)


class Asset(UserOwnedEntity):
    """
    Shared asset model for physical items.

    Used by:
    - home-manager (tools, appliances, home inventory)
    - vehicle-manager (cars, motorcycles)
    - Any service tracking physical assets
    """
    name: str
    description: Optional[str] = None
    asset_type: str  # vehicle, home_item, tool, appliance, etc.
    category: str
    manufacturer: Optional[str] = None
    model_number: Optional[str] = None
    serial_number: Optional[str] = None
    vin: Optional[str] = None  # For vehicles
    purchase_date: Optional[datetime] = None
    purchase_price: Optional[float] = None
    current_value: Optional[float] = None
    condition: AssetCondition = AssetCondition.GOOD
    location: Optional[str] = None
    notes: Optional[str] = None

    # Service-specific context
    context: dict = Field(default_factory=dict)


class MaintenanceRecord(UserOwnedEntity):
    """
    Shared maintenance tracking model.

    Used by:
    - home-manager (home projects)
    - vehicle-manager (vehicle maintenance)
    - Any service tracking maintenance
    """
    asset_id: UUID
    maintenance_type: str
    date: datetime
    cost: Optional[float] = None
    description: Optional[str] = None
    performed_by: Optional[str] = None
    next_due_date: Optional[datetime] = None
    next_due_mileage: Optional[int] = None  # For vehicles
    notes: Optional[str] = None

    # Service-specific context
    context: dict = Field(default_factory=dict)


# Request/Response models for APIs
class TaskCreate(BaseModel):
    """Request model for creating tasks."""
    user_id: str
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.OPEN
    priority: Priority = Priority.MEDIUM
    category: str
    due_date: Optional[datetime] = None
    estimated_minutes: Optional[int] = None
    tags: list[str] = Field(default_factory=list)
    context: dict = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    """Request model for updating tasks."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[Priority] = None
    category: Optional[str] = None
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_minutes: Optional[int] = None
    tags: Optional[list[str]] = None
    context: Optional[dict] = None


class GoalCreate(BaseModel):
    """Request model for creating goals."""
    user_id: str
    title: str
    description: Optional[str] = None
    category: str
    target_value: Optional[float] = None
    target_unit: Optional[str] = None
    target_date: Optional[datetime] = None
    notes: Optional[str] = None
    context: dict = Field(default_factory=dict)


class GoalUpdate(BaseModel):
    """Request model for updating goals."""
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    target_value: Optional[float] = None
    target_unit: Optional[str] = None
    target_date: Optional[datetime] = None
    current_value: Optional[float] = None
    is_active: Optional[bool] = None
    progress_percentage: Optional[int] = None
    notes: Optional[str] = None
    context: Optional[dict] = None


class AssetCreate(BaseModel):
    """Request model for creating assets."""
    user_id: str
    name: str
    description: Optional[str] = None
    asset_type: str
    category: str
    manufacturer: Optional[str] = None
    model_number: Optional[str] = None
    serial_number: Optional[str] = None
    vin: Optional[str] = None
    purchase_date: Optional[datetime] = None
    purchase_price: Optional[float] = None
    condition: AssetCondition = AssetCondition.GOOD
    location: Optional[str] = None
    notes: Optional[str] = None
    context: dict = Field(default_factory=dict)


class AssetUpdate(BaseModel):
    """Request model for updating assets."""
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    manufacturer: Optional[str] = None
    model_number: Optional[str] = None
    serial_number: Optional[str] = None
    current_value: Optional[float] = None
    condition: Optional[AssetCondition] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    context: Optional[dict] = None


class MaintenanceRecordCreate(BaseModel):
    """Request model for creating maintenance records."""
    user_id: str
    asset_id: UUID
    maintenance_type: str
    date: datetime = Field(default_factory=datetime.utcnow)
    cost: Optional[float] = None
    description: Optional[str] = None
    performed_by: Optional[str] = None
    next_due_date: Optional[datetime] = None
    next_due_mileage: Optional[int] = None
    notes: Optional[str] = None
    context: dict = Field(default_factory=dict)


class MaintenanceRecordUpdate(BaseModel):
    """Request model for updating maintenance records."""
    maintenance_type: Optional[str] = None
    date: Optional[datetime] = None
    cost: Optional[float] = None
    description: Optional[str] = None
    performed_by: Optional[str] = None
    next_due_date: Optional[datetime] = None
    next_due_mileage: Optional[int] = None
    notes: Optional[str] = None
    context: Optional[dict] = None
