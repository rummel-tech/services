from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
from enum import Enum
import os


class VehicleType(str, Enum):
    """Vehicle type classification"""
    car = "car"
    motorcycle = "motorcycle"
    truck = "truck"
    suv = "suv"
    van = "van"

# Get the root path from environment variable (for deployment with path prefix)
# Example: /vehicle-manager or empty string for root deployment
ROOT_PATH = os.getenv("ROOT_PATH", "")

app = FastAPI(
    title="Vehicle Manager API",
    version="0.1.0",
    root_path=ROOT_PATH,
    docs_url="/docs" if not ROOT_PATH else f"{ROOT_PATH}/docs",
    openapi_url="/openapi.json" if not ROOT_PATH else f"{ROOT_PATH}/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class Vehicle(BaseModel):
    id: str
    make: str
    model: str
    year: int
    vehicle_type: VehicleType = VehicleType.car
    vin: Optional[str] = None
    license_plate: Optional[str] = None
    current_mileage: int
    color: Optional[str] = None

class MaintenanceRecord(BaseModel):
    id: str
    vehicle_id: str
    date: str
    # Common types: oil_change, tire_rotation, tire_replacement, brake_service, inspection, repair, air_filter
    # Motorcycle-specific: chain_service, valve_adjustment, fork_service, coolant_flush, sprocket_replacement
    type: str
    mileage: int
    cost: Optional[float] = None
    description: Optional[str] = None
    next_due_mileage: Optional[int] = None
    next_due_date: Optional[str] = None

class FuelRecord(BaseModel):
    id: str
    vehicle_id: str
    date: str
    mileage: int
    gallons: float
    cost: float
    price_per_gallon: Optional[float] = None
    fuel_type: Optional[str] = "regular"
    mpg: Optional[float] = None

class MaintenanceSchedule(BaseModel):
    id: str
    vehicle_id: str
    service_type: str
    interval_miles: int
    last_service_mileage: int
    next_due_mileage: int
    status: str  # upcoming, due, overdue

# Default data
def _default_vehicles(user_id: str):
    return {
        "user_id": user_id,
        "vehicles": [
            {
                "id": "v1",
                "make": "Toyota",
                "model": "Camry",
                "year": 2020,
                "vehicle_type": "car",
                "vin": "1HGBH41JXMN109186",
                "license_plate": "ABC-1234",
                "current_mileage": 45000,
                "color": "Silver"
            },
            {
                "id": "v2",
                "make": "Honda",
                "model": "CR-V",
                "year": 2019,
                "vehicle_type": "suv",
                "vin": "2HGFC2F59KH542789",
                "license_plate": "XYZ-5678",
                "current_mileage": 38000,
                "color": "Blue"
            },
            {
                "id": "v3",
                "make": "Harley-Davidson",
                "model": "Street Glide",
                "year": 2022,
                "vehicle_type": "motorcycle",
                "vin": "1HD1KBP19NB123456",
                "license_plate": "MC-9876",
                "current_mileage": 12500,
                "color": "Black"
            },
            {
                "id": "v4",
                "make": "Kawasaki",
                "model": "Ninja 650",
                "year": 2023,
                "vehicle_type": "motorcycle",
                "vin": "JKAEXMJ1XPDA12345",
                "license_plate": "MC-4321",
                "current_mileage": 5200,
                "color": "Green"
            }
        ]
    }

def _default_maintenance_records(vehicle_id: str):
    records = [
        {
            "id": "m1",
            "vehicle_id": vehicle_id,
            "date": "2025-10-15",
            "type": "oil_change",
            "mileage": 42000,
            "cost": 45.99,
            "description": "Synthetic oil change and filter replacement",
            "next_due_mileage": 47000,
            "next_due_date": "2026-04-15"
        },
        {
            "id": "m2",
            "vehicle_id": vehicle_id,
            "date": "2025-09-01",
            "type": "tire_rotation",
            "mileage": 40000,
            "cost": 29.99,
            "description": "Tire rotation and balance",
            "next_due_mileage": 46000,
            "next_due_date": "2026-03-01"
        },
        {
            "id": "m3",
            "vehicle_id": vehicle_id,
            "date": "2025-08-20",
            "type": "inspection",
            "mileage": 39500,
            "cost": 15.00,
            "description": "State safety inspection",
            "next_due_date": "2026-08-20"
        },
        {
            "id": "m4",
            "vehicle_id": vehicle_id,
            "date": "2025-07-10",
            "type": "brake_service",
            "mileage": 38000,
            "cost": 289.50,
            "description": "Front brake pad replacement",
            "next_due_mileage": 58000
        },
    ]
    return {"vehicle_id": vehicle_id, "records": records}

def _default_fuel_records(vehicle_id: str):
    records = [
        {
            "id": "f1",
            "vehicle_id": vehicle_id,
            "date": "2025-11-18",
            "mileage": 45000,
            "gallons": 12.5,
            "cost": 43.75,
            "price_per_gallon": 3.50,
            "fuel_type": "regular",
            "mpg": 28.4
        },
        {
            "id": "f2",
            "vehicle_id": vehicle_id,
            "date": "2025-11-10",
            "mileage": 44645,
            "gallons": 11.8,
            "cost": 41.30,
            "price_per_gallon": 3.50,
            "fuel_type": "regular",
            "mpg": 29.1
        },
        {
            "id": "f3",
            "vehicle_id": vehicle_id,
            "date": "2025-11-03",
            "mileage": 44302,
            "gallons": 12.2,
            "cost": 42.70,
            "price_per_gallon": 3.50,
            "fuel_type": "regular",
            "mpg": 28.8
        },
    ]
    return {"vehicle_id": vehicle_id, "records": records}

def _maintenance_schedule(vehicle_id: str, current_mileage: int):
    schedules = [
        {
            "id": "s1",
            "vehicle_id": vehicle_id,
            "service_type": "Oil Change",
            "interval_miles": 5000,
            "last_service_mileage": 42000,
            "next_due_mileage": 47000,
            "status": "upcoming" if current_mileage < 46000 else "due" if current_mileage < 47500 else "overdue"
        },
        {
            "id": "s2",
            "vehicle_id": vehicle_id,
            "service_type": "Tire Rotation",
            "interval_miles": 6000,
            "last_service_mileage": 40000,
            "next_due_mileage": 46000,
            "status": "upcoming" if current_mileage < 45000 else "due" if current_mileage < 46500 else "overdue"
        },
        {
            "id": "s3",
            "vehicle_id": vehicle_id,
            "service_type": "Air Filter",
            "interval_miles": 15000,
            "last_service_mileage": 30000,
            "next_due_mileage": 45000,
            "status": "due"
        },
    ]
    return {"vehicle_id": vehicle_id, "current_mileage": current_mileage, "schedules": schedules}

def _calculate_stats(vehicle_id: str):
    fuel = _default_fuel_records(vehicle_id)
    maintenance = _default_maintenance_records(vehicle_id)

    total_fuel_cost = sum(r.get("cost", 0) for r in fuel["records"])
    total_gallons = sum(r.get("gallons", 0) for r in fuel["records"])
    avg_mpg = sum(r.get("mpg", 0) for r in fuel["records"]) / len(fuel["records"]) if fuel["records"] else 0
    total_maintenance_cost = sum(r.get("cost", 0) for r in maintenance["records"])

    return {
        "vehicle_id": vehicle_id,
        "fuel": {
            "total_cost": round(total_fuel_cost, 2),
            "total_gallons": round(total_gallons, 2),
            "average_mpg": round(avg_mpg, 1),
            "fill_ups": len(fuel["records"])
        },
        "maintenance": {
            "total_cost": round(total_maintenance_cost, 2),
            "services": len(maintenance["records"]),
            "last_service_date": maintenance["records"][0]["date"] if maintenance["records"] else None
        }
    }

# Endpoints
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/ready")
async def ready():
    return {"status": "ready"}

@app.get("/vehicles/{user_id}")
async def get_vehicles(user_id: str):
    """Get all vehicles for user"""
    return _default_vehicles(user_id)

@app.get("/vehicles/{user_id}/{vehicle_id}")
async def get_vehicle(user_id: str, vehicle_id: str):
    """Get specific vehicle details"""
    vehicles = _default_vehicles(user_id)
    for vehicle in vehicles["vehicles"]:
        if vehicle["id"] == vehicle_id:
            return vehicle
    return {"error": "Vehicle not found"}

@app.get("/maintenance/{vehicle_id}")
async def get_maintenance_records(vehicle_id: str):
    """Get all maintenance records for vehicle"""
    return _default_maintenance_records(vehicle_id)

@app.get("/maintenance/{vehicle_id}/type/{service_type}")
async def get_maintenance_by_type(vehicle_id: str, service_type: str):
    """Get maintenance records by type"""
    all_records = _default_maintenance_records(vehicle_id)
    filtered = [r for r in all_records["records"] if r["type"] == service_type]
    return {"vehicle_id": vehicle_id, "type": service_type, "records": filtered}

@app.get("/fuel/{vehicle_id}")
async def get_fuel_records(vehicle_id: str, limit: Optional[int] = None):
    """Get fuel records for vehicle"""
    records = _default_fuel_records(vehicle_id)
    if limit:
        records["records"] = records["records"][:limit]
    return records

@app.get("/schedule/{vehicle_id}")
async def get_maintenance_schedule(vehicle_id: str):
    """Get maintenance schedule for vehicle"""
    # Get current mileage from vehicles
    vehicles = _default_vehicles("user-123")
    current_mileage = 45000
    for v in vehicles["vehicles"]:
        if v["id"] == vehicle_id:
            current_mileage = v["current_mileage"]
            break

    return _maintenance_schedule(vehicle_id, current_mileage)

@app.get("/stats/{vehicle_id}")
async def get_vehicle_stats(vehicle_id: str):
    """Get statistics for vehicle"""
    return _calculate_stats(vehicle_id)

@app.get("/summary/{user_id}")
async def get_user_summary(user_id: str):
    """Get summary for all user vehicles"""
    vehicles = _default_vehicles(user_id)
    total_vehicles = len(vehicles["vehicles"])

    # Calculate total costs across all vehicles
    total_fuel_cost = 0
    total_maintenance_cost = 0

    for vehicle in vehicles["vehicles"]:
        stats = _calculate_stats(vehicle["id"])
        total_fuel_cost += stats["fuel"]["total_cost"]
        total_maintenance_cost += stats["maintenance"]["total_cost"]

    return {
        "user_id": user_id,
        "total_vehicles": total_vehicles,
        "total_fuel_cost": round(total_fuel_cost, 2),
        "total_maintenance_cost": round(total_maintenance_cost, 2),
        "total_cost": round(total_fuel_cost + total_maintenance_cost, 2)
    }
