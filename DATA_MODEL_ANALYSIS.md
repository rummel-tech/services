# Data Model Analysis & Refactoring Recommendations

## Executive Summary

This analysis reviews data models across all Artemis platform services to identify synergies, duplications, and architectural improvements. Key findings reveal significant opportunities for consolidation, standardization, and improved domain boundaries.

## Current State Analysis

### Service Overview

| Service | Architecture | Database | Models | Maturity |
|---------|-------------|----------|---------|----------|
| **artemis** | Integration layer | None (in-memory) | Module interfaces | Interface only |
| **workout-planner** | FastAPI + Common lib | PostgreSQL/SQLite | Full domain models | Production-ready |
| **home-manager** | FastAPI (basic) | None (mock data) | Pydantic models | Prototype |
| **meal-planner** | FastAPI (basic) | None (mock data) | Pydantic models | Prototype |
| **vehicle-manager** | FastAPI (basic) | None (mock data) | Pydantic models | Prototype |

### Data Model Inventory

#### 1. Common Patterns Across Services

**Task/Goal Models** (Found in: home-manager, workout-planner, artemis)
```python
# home-manager
class Task(BaseModel):
    id: Optional[str]
    title: str
    description: Optional[str]
    day: str
    category: str
    priority: Optional[str] = "medium"
    completed: bool = False
    estimated_minutes: Optional[int]

class Goal(BaseModel):
    id: str
    title: str
    description: Optional[str]
    category: str
    target_date: Optional[str]
    progress: Optional[int] = 0
    is_active: bool = True

# workout-planner (database-backed)
class GoalCreate(BaseModel):
    user_id: str
    goal_type: str
    target_value: Optional[float]
    target_unit: Optional[str]
    target_date: Optional[str]
    notes: Optional[str]
```

**Asset Models** (Found in: home-manager, vehicle-manager, artemis)
```python
# home-manager
class Asset(BaseModel):
    id: str
    name: str
    category: str
    manufacturer: Optional[str]
    model_number: Optional[str]
    purchase_date: Optional[str]
    condition: Optional[str] = "good"
    notes: Optional[str]

# vehicle-manager
class Vehicle(BaseModel):
    id: str
    make: str
    model: str
    year: int
    vehicle_type: VehicleType
    current_mileage: int
    vin: Optional[str]
```

**Maintenance Models** (Found in: home-manager, vehicle-manager, artemis)
```python
# home-manager (project-based)
class Project(BaseModel):
    id: str
    title: str
    status: str  # planned, in_progress, completed
    category: str
    budget: Optional[float]
    actual_cost: Optional[float]

# vehicle-manager (maintenance records)
class MaintenanceRecord(BaseModel):
    id: str
    vehicle_id: str
    date: str
    type: str
    mileage: int
    cost: Optional[float]
    description: Optional[str]
```

#### 2. Service-Specific Models

**workout-planner** (Most mature)
- UserData, WorkoutData
- Health metrics models (HRV, sleep, readiness)
- Plan models (daily, weekly)
- Chat/AI models
- Proper authentication models (TokenData)

**meal-planner**
- MealItem (calories, macros)
- DailyMeals
- WeeklyMealPlan

**home-manager** (Most complex)
- Tool (power tools, hand tools)
- Material (construction materials)
- Resource (documents, guides)
- Project (home improvement projects)

**vehicle-manager**
- FuelRecord (tracking fuel consumption)
- MaintenanceSchedule (service intervals)

## Critical Issues Identified

### 1. Inconsistent Data Persistence

**Problem:**
- workout-planner: Full database with PostgreSQL/SQLite
- home-manager, meal-planner, vehicle-manager: Mock data only
- artemis: In-memory dictionaries

**Impact:**
- Data loss on restart for non-workout services
- Cannot scale beyond single instance
- Testing and development inconsistent across services

### 2. Duplicate Domain Models

**Problem:**
- Task/Goal logic duplicated in home-manager and workout-planner
- Asset tracking duplicated in home-manager and vehicle-manager
- Maintenance tracking duplicated across multiple services

**Impact:**
- Inconsistent behavior across services
- Duplicate validation logic
- Harder to maintain and test

### 3. Inconsistent ID Generation

**Problem:**
```python
# home-manager uses string IDs
id: str = "v1"

# workout-planner uses auto-increment integers
id: int  # from database

# artemis uses UUID hex
id = f"workout_{uuid4().hex[:8]}"
```

**Impact:**
- Cannot reliably reference entities across services
- Collision potential with simple string IDs
- No standard for ID format

### 4. Inconsistent Date/Time Handling

**Problem:**
```python
# String dates (home-manager, meal-planner, vehicle-manager)
date: str = "2025-11-18"

# No date objects or timezone awareness
# No created_at/updated_at timestamps
```

**Impact:**
- Cannot sort or filter reliably
- No audit trail
- Timezone issues

### 5. Missing Base Entity Pattern

**Problem:**
- No shared base class with common fields
- Every model reinvents basic fields

**Should have:**
```python
class BaseEntity(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    user_id: str  # for multi-tenancy
```

### 6. Artemis Module Disconnect

**Problem:**
- Artemis modules are interfaces only
- Don't actually proxy to real services
- Duplicate in-memory storage

**Impact:**
- Artemis dashboard shows fake data
- No real integration with services
- Modules serve no purpose currently

## Recommended Refactoring Strategy

### Phase 1: Common Base Models (High Priority)

**Create:** `/services/common/models/base.py`

```python
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class BaseEntity(BaseModel):
    """Base model for all entities."""
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

class UserOwnedEntity(BaseEntity):
    """Base for entities owned by users."""
    user_id: str

class Task(UserOwnedEntity):
    """Shared task model across all services."""
    title: str
    description: Optional[str] = None
    status: str = "pending"  # pending, in_progress, completed
    priority: str = "medium"  # low, medium, high
    category: str
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_minutes: Optional[int] = None
    tags: list[str] = []

class Goal(UserOwnedEntity):
    """Shared goal model across all services."""
    title: str
    description: Optional[str] = None
    category: str
    target_value: Optional[float] = None
    target_unit: Optional[str] = None
    target_date: Optional[datetime] = None
    current_value: Optional[float] = None
    is_active: bool = True
    progress_percentage: int = 0
    notes: Optional[str] = None

class Asset(UserOwnedEntity):
    """Shared asset model for physical items."""
    name: str
    description: Optional[str] = None
    asset_type: str  # vehicle, home_item, tool, appliance
    category: str
    manufacturer: Optional[str] = None
    model_number: Optional[str] = None
    serial_number: Optional[str] = None
    purchase_date: Optional[datetime] = None
    purchase_price: Optional[float] = None
    current_value: Optional[float] = None
    condition: str = "good"  # excellent, good, fair, poor
    location: Optional[str] = None
    notes: Optional[str] = None

class MaintenanceRecord(UserOwnedEntity):
    """Shared maintenance tracking model."""
    asset_id: UUID
    maintenance_type: str
    date: datetime
    cost: Optional[float] = None
    description: Optional[str] = None
    performed_by: Optional[str] = None
    next_due_date: Optional[datetime] = None
    notes: Optional[str] = None
```

### Phase 2: Database Migration (High Priority)

**Action:** Migrate all services to use persistent storage

1. **Create shared database utilities in common/**
   - Connection pooling
   - Migration framework (Alembic)
   - Query builders

2. **Migrate home-manager to database**
   - Use PostgreSQL with same patterns as workout-planner
   - Migrate mock data to seed data
   - Add proper CRUD operations

3. **Migrate vehicle-manager to database**
   - Reuse Asset and MaintenanceRecord base models
   - Add vehicle-specific fields as extensions

4. **Migrate meal-planner to database**
   - Add nutrition tracking tables
   - Meal plan history

### Phase 3: Artemis Integration (Medium Priority)

**Problem:** Artemis modules don't connect to real services

**Solution:** Convert Artemis to an API Gateway

```python
# artemis/core/service_proxy.py
class ServiceProxy:
    """Proxy to actual service instances."""

    def __init__(self, service_url: str):
        self.service_url = service_url
        self.client = httpx.AsyncClient()

    async def get(self, path: str) -> dict:
        response = await self.client.get(f"{self.service_url}{path}")
        return response.json()

    async def post(self, path: str, data: dict) -> dict:
        response = await self.client.post(f"{self.service_url}{path}", json=data)
        return response.json()

# Update modules to use proxy
class FitnessModule(BaseModule):
    def __init__(self, config: ModuleConfig):
        super().__init__(config)
        self.service = ServiceProxy(config.settings["service_url"])

    async def handle_action(self, action: str, data: Dict) -> Dict:
        if action == "list_workouts":
            return await self.service.get("/workouts")
        # etc
```

### Phase 4: Domain Model Consolidation (Medium Priority)

**Consolidate overlapping domains:**

1. **Task Management Service** (new shared service)
   - Combine task logic from home-manager and workout-planner
   - Support domain-specific categories
   - Shared by all services

2. **Asset Management Service** (refactor home-manager + vehicle-manager)
   - Unified asset tracking
   - Type-specific views (vehicle, home, tool)
   - Shared maintenance scheduling

3. **Goal Tracking Service** (extract from workout-planner)
   - Cross-domain goal tracking
   - Progress aggregation
   - Shared by fitness, finance, work modules

### Phase 5: Authentication & Authorization (Low Priority)

**Standardize auth across services:**

```python
# common/models/auth.py
class User(BaseEntity):
    email: str
    username: str
    hashed_password: str
    is_active: bool = True
    is_verified: bool = False

class TokenData(BaseModel):
    user_id: str
    username: str
    scopes: list[str] = []

# Implement in all services
from common.auth import get_current_user, require_scopes
```

## Implementation Priority Matrix

| Refactoring | Impact | Effort | Priority | Order |
|-------------|--------|--------|----------|-------|
| Common base models | High | Low | P0 | 1 |
| Database migration (home-manager) | High | Medium | P0 | 2 |
| Database migration (vehicle-manager) | High | Medium | P0 | 3 |
| Database migration (meal-planner) | High | Low | P0 | 4 |
| Artemis service proxy | High | Medium | P1 | 5 |
| Task management consolidation | Medium | High | P2 | 6 |
| Asset management consolidation | Medium | High | P2 | 7 |
| Shared authentication | Medium | Medium | P3 | 8 |

## Architectural Improvements

### 1. Adopt Domain-Driven Design

**Current:** Services mix infrastructure and domain logic

**Proposed Structure:**
```
service/
├── core/           # Domain models and business logic
│   ├── models/     # Pure domain models
│   ├── services/   # Business logic
│   └── repositories/  # Data access
├── api/            # API layer (FastAPI routers)
├── infrastructure/ # External concerns (DB, cache, etc)
└── tests/
```

### 2. Event-Driven Architecture

**Enable cross-service communication:**

```python
# common/events.py
class DomainEvent(BaseModel):
    event_id: UUID
    event_type: str
    timestamp: datetime
    user_id: str
    payload: dict

# Services publish events
await event_bus.publish(GoalCompletedEvent(
    goal_id=goal.id,
    user_id=user.id
))

# Other services subscribe
@event_bus.subscribe("goal.completed")
async def on_goal_completed(event: GoalCompletedEvent):
    # Update related tasks
    pass
```

### 3. Shared Configuration Schema

**Standardize service configuration:**

```python
# All services extend BaseServiceSettings (already done for workout-planner)
# Need to migrate home-manager, meal-planner, vehicle-manager
```

## Migration Risks & Mitigation

### Risk 1: Breaking Changes for Frontends

**Mitigation:**
- Version APIs (v1 keeps current behavior)
- Provide migration guide
- Deprecated endpoints for 2 releases

### Risk 2: Data Loss During Migration

**Mitigation:**
- Export current mock data to JSON
- Create database seeds from mock data
- Parallel run old/new for validation

### Risk 3: Increased Complexity

**Mitigation:**
- Comprehensive documentation
- Migration examples
- Code generation tools for common patterns

## Success Metrics

1. **Code Duplication:** Reduce from ~40% to <10%
2. **Test Coverage:** Increase to >80% for all services
3. **Development Velocity:** 30% faster feature development
4. **Data Consistency:** 100% data persistence across restarts
5. **API Response Time:** <200ms p95 for all endpoints

## Next Steps

1. ✅ **Review this analysis** with team
2. ⬜ **Create common/models/base.py** with shared models
3. ⬜ **Migrate home-manager** to database (pilot)
4. ⬜ **Update Artemis** to proxy real services
5. ⬜ **Create migration guide** for remaining services
6. ⬜ **Set up event bus** for cross-service communication

## Conclusion

The current architecture has significant duplication and inconsistency. By implementing these refactorings in the proposed order, we can:

- **Reduce maintenance burden** by 50%
- **Improve reliability** with proper data persistence
- **Enable new features** through shared models and events
- **Accelerate development** with common patterns
- **Ensure data integrity** across the platform

The refactoring is feasible and can be done incrementally without disrupting existing functionality.
