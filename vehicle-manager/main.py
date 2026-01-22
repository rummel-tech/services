"""
Vehicle Manager API - Vehicle fleet management service.

Refactored to use common models and database persistence.
Supports cars, motorcycles, trucks, and other vehicles.
"""

import sys
from pathlib import Path
from typing import List, Optional
from uuid import UUID
from datetime import datetime

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from common.models import (
    Asset, MaintenanceRecord,
    AssetCreate, AssetUpdate,
    MaintenanceRecordCreate, MaintenanceRecordUpdate,
    AssetCondition
)
from common.database import (
    get_connection, get_cursor, dict_from_row,
    init_db, close_db, adapt_query, is_sqlite, get_database_url
)

# Initialize FastAPI app
app = FastAPI(
    title="Vehicle Manager API",
    version="2.0.0",
    description="Vehicle fleet management service with database persistence"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Check if using SQLite for query adaptation
USE_SQLITE = is_sqlite(get_database_url())


# Additional models for vehicle-specific features
class FuelRecord(BaseModel):
    """Fuel record for tracking vehicle fuel consumption."""
    id: UUID
    user_id: str
    asset_id: UUID
    date: datetime
    mileage: int
    gallons: float
    cost: float
    price_per_gallon: Optional[float] = None
    fuel_type: str = "regular"
    mpg: Optional[float] = None
    notes: Optional[str] = None


class FuelRecordCreate(BaseModel):
    """Request model for creating fuel records."""
    user_id: str
    asset_id: UUID
    date: datetime
    mileage: int
    gallons: float
    cost: float
    price_per_gallon: Optional[float] = None
    fuel_type: str = "regular"
    notes: Optional[str] = None


# Startup/shutdown events
@app.on_event("startup")
async def startup():
    """Initialize database connection pool."""
    init_db()


@app.on_event("shutdown")
async def shutdown():
    """Close database connection pool."""
    close_db()


# ============================================================================
# Health Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "vehicle-manager"}


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    return {"status": "ready", "database": get_database_url()}


# ============================================================================
# Vehicle Endpoints (using common Asset model)
# ============================================================================

@app.get("/vehicles/{user_id}", response_model=List[Asset])
async def list_vehicles(user_id: str):
    """List all vehicles for a user."""
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query(
            "SELECT * FROM assets WHERE user_id = %s AND asset_type = 'vehicle' ORDER BY created_at DESC",
            USE_SQLITE
        )
        cur.execute(query, (user_id,))
        rows = cur.fetchall()
        return [Asset(**dict_from_row(row, USE_SQLITE)) for row in rows]


@app.post("/vehicles", response_model=Asset, status_code=status.HTTP_201_CREATED)
async def create_vehicle(vehicle: AssetCreate):
    """Create a new vehicle."""
    # Force asset_type to 'vehicle'
    vehicle.asset_type = "vehicle"

    with get_connection() as conn:
        cur = get_cursor(conn)

        if USE_SQLITE:
            import uuid
            vehicle_id = str(uuid.uuid4())
            query = """INSERT INTO assets (id, user_id, name, description, asset_type, category,
                                           manufacturer, model_number, serial_number, vin,
                                           purchase_date, purchase_price, condition, location, notes, context)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            cur.execute(query, (
                vehicle_id, vehicle.user_id, vehicle.name, vehicle.description, vehicle.asset_type,
                vehicle.category, vehicle.manufacturer, vehicle.model_number, vehicle.serial_number,
                vehicle.vin, vehicle.purchase_date, vehicle.purchase_price, vehicle.condition.value,
                vehicle.location, vehicle.notes, str(vehicle.context)
            ))
            cur.execute("SELECT * FROM assets WHERE id = ?", (vehicle_id,))
        else:
            query = """INSERT INTO assets (id, user_id, name, description, asset_type, category,
                                           manufacturer, model_number, serial_number, vin,
                                           purchase_date, purchase_price, condition, location, notes, context)
                       VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING *"""
            cur.execute(query, (
                vehicle.user_id, vehicle.name, vehicle.description, vehicle.asset_type,
                vehicle.category, vehicle.manufacturer, vehicle.model_number, vehicle.serial_number,
                vehicle.vin, vehicle.purchase_date, vehicle.purchase_price, vehicle.condition.value,
                vehicle.location, vehicle.notes, vehicle.context
            ))

        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create vehicle")
        return Asset(**dict_from_row(row, USE_SQLITE))


@app.get("/vehicles/{user_id}/{vehicle_id}", response_model=Asset)
async def get_vehicle(user_id: str, vehicle_id: UUID):
    """Get a specific vehicle."""
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query(
            "SELECT * FROM assets WHERE id = %s AND user_id = %s AND asset_type = 'vehicle'",
            USE_SQLITE
        )
        cur.execute(query, (str(vehicle_id), user_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        return Asset(**dict_from_row(row, USE_SQLITE))


# ============================================================================
# Maintenance Endpoints (using common MaintenanceRecord model)
# ============================================================================

@app.get("/maintenance/{vehicle_id}", response_model=List[MaintenanceRecord])
async def list_maintenance(vehicle_id: UUID):
    """List all maintenance records for a vehicle."""
    with get_connection() as conn:
        cur = get_cursor(conn)
        query = adapt_query(
            "SELECT * FROM maintenance_records WHERE asset_id = %s ORDER BY date DESC",
            USE_SQLITE
        )
        cur.execute(query, (str(vehicle_id),))
        rows = cur.fetchall()
        return [MaintenanceRecord(**dict_from_row(row, USE_SQLITE)) for row in rows]


@app.post("/maintenance", response_model=MaintenanceRecord, status_code=status.HTTP_201_CREATED)
async def create_maintenance(maintenance: MaintenanceRecordCreate):
    """Create a new maintenance record."""
    with get_connection() as conn:
        cur = get_cursor(conn)

        if USE_SQLITE:
            import uuid
            record_id = str(uuid.uuid4())
            query = """INSERT INTO maintenance_records (id, user_id, asset_id, maintenance_type, date,
                                                        cost, description, performed_by, next_due_date,
                                                        next_due_mileage, notes, context)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            cur.execute(query, (
                record_id, maintenance.user_id, str(maintenance.asset_id), maintenance.maintenance_type,
                maintenance.date, maintenance.cost, maintenance.description, maintenance.performed_by,
                maintenance.next_due_date, maintenance.next_due_mileage, maintenance.notes, str(maintenance.context)
            ))
            cur.execute("SELECT * FROM maintenance_records WHERE id = ?", (record_id,))
        else:
            query = """INSERT INTO maintenance_records (id, user_id, asset_id, maintenance_type, date,
                                                        cost, description, performed_by, next_due_date,
                                                        next_due_mileage, notes, context)
                       VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING *"""
            cur.execute(query, (
                maintenance.user_id, maintenance.asset_id, maintenance.maintenance_type,
                maintenance.date, maintenance.cost, maintenance.description, maintenance.performed_by,
                maintenance.next_due_date, maintenance.next_due_mileage, maintenance.notes, maintenance.context
            ))

        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create maintenance record")
        return MaintenanceRecord(**dict_from_row(row, USE_SQLITE))


# ============================================================================
# Fuel Record Endpoints
# ============================================================================

@app.get("/fuel/{vehicle_id}", response_model=List[FuelRecord])
async def list_fuel_records(vehicle_id: UUID, limit: Optional[int] = None):
    """List fuel records for a vehicle."""
    with get_connection() as conn:
        cur = get_cursor(conn)

        if limit:
            query = adapt_query(
                "SELECT * FROM fuel_records WHERE asset_id = %s ORDER BY date DESC LIMIT %s",
                USE_SQLITE
            )
            cur.execute(query, (str(vehicle_id), limit))
        else:
            query = adapt_query(
                "SELECT * FROM fuel_records WHERE asset_id = %s ORDER BY date DESC",
                USE_SQLITE
            )
            cur.execute(query, (str(vehicle_id),))

        rows = cur.fetchall()
        return [FuelRecord(**dict_from_row(row, USE_SQLITE)) for row in rows]


@app.post("/fuel", response_model=FuelRecord, status_code=status.HTTP_201_CREATED)
async def create_fuel_record(fuel: FuelRecordCreate):
    """Create a new fuel record."""
    # Calculate MPG if not provided
    mpg = None
    if fuel.price_per_gallon is None and fuel.gallons > 0:
        fuel.price_per_gallon = fuel.cost / fuel.gallons

    with get_connection() as conn:
        cur = get_cursor(conn)

        if USE_SQLITE:
            import uuid
            record_id = str(uuid.uuid4())
            query = """INSERT INTO fuel_records (id, user_id, asset_id, date, mileage, gallons, cost,
                                                 price_per_gallon, fuel_type, mpg, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            cur.execute(query, (
                record_id, fuel.user_id, str(fuel.asset_id), fuel.date, fuel.mileage,
                fuel.gallons, fuel.cost, fuel.price_per_gallon, fuel.fuel_type, mpg, fuel.notes
            ))
            cur.execute("SELECT * FROM fuel_records WHERE id = ?", (record_id,))
        else:
            query = """INSERT INTO fuel_records (id, user_id, asset_id, date, mileage, gallons, cost,
                                                 price_per_gallon, fuel_type, mpg, notes)
                       VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING *"""
            cur.execute(query, (
                fuel.user_id, fuel.asset_id, fuel.date, fuel.mileage,
                fuel.gallons, fuel.cost, fuel.price_per_gallon, fuel.fuel_type, mpg, fuel.notes
            ))

        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create fuel record")
        return FuelRecord(**dict_from_row(row, USE_SQLITE))


# ============================================================================
# Statistics Endpoints
# ============================================================================

@app.get("/stats/{vehicle_id}")
async def get_vehicle_stats(vehicle_id: UUID):
    """Get statistics for a vehicle."""
    with get_connection() as conn:
        cur = get_cursor(conn)

        # Fuel stats
        query = adapt_query(
            """SELECT COUNT(*) as fill_ups, SUM(cost) as total_cost, SUM(gallons) as total_gallons,
                      AVG(mpg) as avg_mpg
               FROM fuel_records WHERE asset_id = %s""",
            USE_SQLITE
        )
        cur.execute(query, (str(vehicle_id),))
        fuel_stats = dict_from_row(cur.fetchone(), USE_SQLITE)

        # Maintenance stats
        query = adapt_query(
            """SELECT COUNT(*) as services, SUM(cost) as total_cost, MAX(date) as last_service
               FROM maintenance_records WHERE asset_id = %s""",
            USE_SQLITE
        )
        cur.execute(query, (str(vehicle_id),))
        maint_stats = dict_from_row(cur.fetchone(), USE_SQLITE)

        return {
            "vehicle_id": str(vehicle_id),
            "fuel": {
                "total_cost": fuel_stats.get("total_cost") or 0,
                "total_gallons": fuel_stats.get("total_gallons") or 0,
                "average_mpg": fuel_stats.get("avg_mpg") or 0,
                "fill_ups": fuel_stats.get("fill_ups") or 0,
            },
            "maintenance": {
                "total_cost": maint_stats.get("total_cost") or 0,
                "services": maint_stats.get("services") or 0,
                "last_service_date": maint_stats.get("last_service"),
            }
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8030)
