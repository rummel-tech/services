from typing import List, Optional
from pydantic import BaseModel


# ── Trips ──────────────────────────────────────────────────────────────────────

class TripCreate(BaseModel):
    name: str
    destination: str
    trip_type: str = "vacation"  # road_trip | flight | vacation | business | weekend | camping | international
    start_date: Optional[str] = None   # YYYY-MM-DD
    end_date: Optional[str] = None     # YYYY-MM-DD
    budget_cents: int = 0
    notes: Optional[str] = None


class TripUpdate(BaseModel):
    name: Optional[str] = None
    destination: Optional[str] = None
    trip_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    budget_cents: Optional[int] = None
    notes: Optional[str] = None
    status: Optional[str] = None  # planning | active | completed


class TripResponse(BaseModel):
    id: str
    user_id: str
    name: str
    destination: str
    trip_type: str
    start_date: Optional[str]
    end_date: Optional[str]
    budget_cents: int
    notes: Optional[str]
    status: str
    # Computed
    total_days: int
    spent_cents: int
    remaining_cents: int
    created_at: str
    updated_at: str


# ── Itinerary ──────────────────────────────────────────────────────────────────

class ItineraryItemCreate(BaseModel):
    day_date: str                       # YYYY-MM-DD
    title: str
    location: Optional[str] = None
    start_time: Optional[str] = None    # HH:MM (24h)
    end_time: Optional[str] = None
    category: str = "activity"          # accommodation | transport | food | activity | other
    notes: Optional[str] = None
    cost_cents: int = 0


class ItineraryItemUpdate(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    cost_cents: Optional[int] = None
    position: Optional[int] = None


class ItineraryItemResponse(BaseModel):
    id: str
    trip_id: str
    day_date: str
    title: str
    location: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]
    category: str
    notes: Optional[str]
    cost_cents: int
    position: int
    created_at: str


class ItineraryDayResponse(BaseModel):
    date: str
    items: List[ItineraryItemResponse]


# ── Packing ────────────────────────────────────────────────────────────────────

class PackingItemCreate(BaseModel):
    category: str = "general"   # clothing | toiletries | documents | electronics | gear | food | general
    name: str
    quantity: int = 1


class PackingItemUpdate(BaseModel):
    category: Optional[str] = None
    name: Optional[str] = None
    quantity: Optional[int] = None
    packed: Optional[bool] = None


class PackingItemResponse(BaseModel):
    id: str
    trip_id: str
    category: str
    name: str
    quantity: int
    packed: bool
    added_at: str


# ── Expenses ───────────────────────────────────────────────────────────────────

class ExpenseCreate(BaseModel):
    category: str = "misc"  # accommodation | transport | food | activities | shopping | misc
    description: str
    amount_cents: int
    expense_date: str       # YYYY-MM-DD


class ExpenseUpdate(BaseModel):
    category: Optional[str] = None
    description: Optional[str] = None
    amount_cents: Optional[int] = None
    expense_date: Optional[str] = None


class ExpenseResponse(BaseModel):
    id: str
    trip_id: str
    category: str
    description: str
    amount_cents: int
    expense_date: str
    added_at: str


class BudgetSummaryResponse(BaseModel):
    budget_cents: int
    spent_cents: int
    remaining_cents: int
    by_category: dict
