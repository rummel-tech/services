"""Artemis platform integration router for Vehicle Manager.

Implements the Artemis Module Contract v1.0:
  GET  /artemis/manifest
  GET  /artemis/widgets/{widget_id}
  POST /artemis/agent/{tool_id}
  GET  /artemis/data/{data_id}
"""
import os
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from common.database import adapt_query, dict_from_row, get_connection, get_cursor, get_database_url, is_sqlite

USE_SQLITE = is_sqlite(get_database_url())
router = APIRouter(prefix="/artemis", tags=["artemis"])

ARTEMIS_AUTH_URL = os.getenv("ARTEMIS_AUTH_URL", "http://localhost:8090")
_artemis_public_key: Optional[str] = None
_artemis_public_key_fetched_at: float = 0.0
_KEY_CACHE_TTL = 86400  # 24 hours


def _fetch_artemis_public_key() -> Optional[str]:
    global _artemis_public_key, _artemis_public_key_fetched_at
    now = time.time()
    if _artemis_public_key and (now - _artemis_public_key_fetched_at) < _KEY_CACHE_TTL:
        return _artemis_public_key
    try:
        r = httpx.get(f"{ARTEMIS_AUTH_URL}/auth/public-key", timeout=3.0)
        if r.status_code == 200:
            _artemis_public_key = r.json()["public_key"]
            _artemis_public_key_fetched_at = now
            return _artemis_public_key
    except Exception:
        pass
    return None


class _TokenData(BaseModel):
    user_id: str
    email: str = ""


def require_token(authorization: Optional[str] = Header(None)) -> _TokenData:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    raw = authorization.split(" ", 1)[1]
    try:
        unverified = jwt.get_unverified_claims(raw)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if unverified.get("iss") == "artemis-auth":
        pub_key = _fetch_artemis_public_key()
        if pub_key:
            try:
                payload = jwt.decode(raw, pub_key, algorithms=["RS256"], issuer="artemis-auth")
                return _TokenData(user_id=payload["sub"], email=payload.get("email", ""))
            except JWTError as e:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
        # Dev fallback: auth service not running — only permitted outside production
        if os.getenv("ENVIRONMENT", "development") != "production":
            return _TokenData(user_id=unverified.get("sub", "dev-user"), email=unverified.get("email", ""))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service unavailable")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported token issuer")


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

MANIFEST = {
    "module": {
        "id": "vehicle-manager",
        "name": "Vehicle Manager",
        "version": "1.0.0",
        "contract_version": "1.0",
        "description": "Vehicle fleet tracking, maintenance, and fuel logging",
        "icon": "directions_car",
        "color": "#0ea5e9",
        "standalone_url": "https://rummel-tech.github.io/vehicle-manager/",
        "api_base": "https://api.rummeltech.com/vehicle-manager",
    },
    "capabilities": {
        "auth": {"accepts_artemis_token": True, "standalone_auth": False},
        "dashboard_widgets": [
            {
                "id": "fleet_overview",
                "name": "Fleet Overview",
                "description": "Summary of all vehicles",
                "size": "small",
                "data_endpoint": "/artemis/widgets/fleet_overview",
                "refresh_seconds": 3600,
            },
            {
                "id": "upcoming_maintenance",
                "name": "Upcoming Maintenance",
                "description": "Next scheduled maintenance items",
                "size": "medium",
                "data_endpoint": "/artemis/widgets/upcoming_maintenance",
                "refresh_seconds": 3600,
            },
        ],
        "quick_actions": [
            {
                "id": "log_fuel",
                "label": "Log Fuel",
                "icon": "local_gas_station",
                "endpoint": "/artemis/agent/log_fuel",
                "method": "POST",
            },
        ],
        "provides_data": [
            {
                "id": "fuel_costs",
                "name": "Monthly Fuel Costs",
                "description": "Rolling fuel spend across all vehicles",
                "endpoint": "/artemis/data/fuel_costs",
                "schema": {"total_cost": "number", "total_gallons": "number", "avg_mpg": "number"},
                "requires_permission": "vehicle.fuel.read",
            },
            {
                "id": "maintenance_costs",
                "name": "Maintenance Costs",
                "description": "Rolling maintenance spend across all vehicles",
                "endpoint": "/artemis/data/maintenance_costs",
                "schema": {"total_cost": "number", "service_count": "number"},
                "requires_permission": "vehicle.maintenance.read",
            },
        ],
        "agent_tools": [
            {
                "id": "list_vehicles",
                "description": "List all vehicles in the user's fleet",
                "endpoint": "/artemis/agent/list_vehicles",
                "method": "GET",
                "parameters": {},
            },
            {
                "id": "log_fuel",
                "description": "Log a fuel fill-up for a vehicle",
                "endpoint": "/artemis/agent/log_fuel",
                "method": "POST",
                "parameters": {
                    "vehicle_id": {"type": "string", "required": True},
                    "mileage": {"type": "number", "description": "Current odometer reading", "required": True},
                    "gallons": {"type": "number", "required": True},
                    "cost": {"type": "number", "description": "Total cost of fill-up", "required": True},
                    "fuel_type": {"type": "string", "description": "regular, premium, diesel", "required": False},
                    "notes": {"type": "string", "required": False},
                },
            },
            {
                "id": "log_maintenance",
                "description": "Log a maintenance service for a vehicle",
                "endpoint": "/artemis/agent/log_maintenance",
                "method": "POST",
                "parameters": {
                    "vehicle_id": {"type": "string", "required": True},
                    "maintenance_type": {"type": "string", "description": "oil_change, tire_rotation, brakes, etc.", "required": True},
                    "cost": {"type": "number", "required": False},
                    "description": {"type": "string", "required": False},
                    "next_due_date": {"type": "string", "description": "ISO date for next service", "required": False},
                },
            },
            {
                "id": "get_vehicle_stats",
                "description": "Get fuel efficiency and maintenance stats for a vehicle",
                "endpoint": "/artemis/agent/get_vehicle_stats",
                "method": "POST",
                "parameters": {
                    "vehicle_id": {"type": "string", "required": True},
                },
            },
        ],
    },
}


@router.get("/manifest")
def get_manifest() -> dict:
    return MANIFEST


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(sql: str, params: tuple) -> list[dict]:
    with get_connection() as conn:
        cur = get_cursor(conn, dict_cursor=not USE_SQLITE)
        if USE_SQLITE:
            sql = sql.replace("%s", "?")
        cur.execute(sql, params)
        rows = cur.fetchall()
        if USE_SQLITE:
            return [dict(zip([d[0] for d in cur.description], row)) for row in rows]
        return [dict(row) for row in rows]



def _vehicles_for_user(user_id: str) -> list:
    rows = _q(
        "SELECT id, name, manufacturer, model_number, condition, notes FROM assets WHERE user_id = %s AND asset_type = 'vehicle' ORDER BY name",
        (user_id,),
    )
    return list(rows)


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

@router.get("/widgets/{widget_id}")
def get_widget(widget_id: str, token: _TokenData = Depends(require_token)) -> dict:
    now = datetime.now(timezone.utc).isoformat() + "Z"
    user_id = token.user_id

    if widget_id == "fleet_overview":
        vehicles = _vehicles_for_user(user_id)
        conditions = {}
        for v in vehicles:
            c = v.get("condition", "unknown")
            conditions[c] = conditions.get(c, 0) + 1
        return {
            "widget_id": "fleet_overview",
            "data": {"vehicle_count": len(vehicles), "vehicles": vehicles[:3], "conditions": conditions},
            "last_updated": now,
        }

    if widget_id == "upcoming_maintenance":
        vehicles = _vehicles_for_user(user_id)
        upcoming = []
        today = str(date.today())
        for v in vehicles:
            rows = _q(
                "SELECT maintenance_type, next_due_date, cost FROM maintenance_records WHERE asset_id = %s AND next_due_date >= %s ORDER BY next_due_date ASC LIMIT 1",
                (v["id"], today),
            )
            for r in rows:
                upcoming.append({"vehicle_name": v["name"], **r})
        upcoming.sort(key=lambda x: x.get("next_due_date") or "9999")
        return {
            "widget_id": "upcoming_maintenance",
            "data": {"items": upcoming[:5], "count": len(upcoming)},
            "last_updated": now,
        }

    raise HTTPException(status_code=404, detail=f"Unknown widget: {widget_id}")


# ---------------------------------------------------------------------------
# Agent tools
# ---------------------------------------------------------------------------

@router.get("/agent/list_vehicles")
@router.post("/agent/list_vehicles")
def agent_list_vehicles(token: _TokenData = Depends(require_token)) -> dict:
    vehicles = _vehicles_for_user(token.user_id)
    return {"success": True, "result": {"vehicles": vehicles, "count": len(vehicles)}}


@router.post("/agent/log_fuel")
def agent_log_fuel(body: dict, token: _TokenData = Depends(require_token)) -> dict:
    vehicle_id = body.get("vehicle_id")
    mileage = body.get("mileage")
    gallons = body.get("gallons")
    cost = body.get("cost")

    if not vehicle_id:
        raise HTTPException(status_code=400, detail="vehicle_id is required")
    if mileage is None:
        raise HTTPException(status_code=400, detail="mileage is required")
    if gallons is None:
        raise HTTPException(status_code=400, detail="gallons is required")
    if cost is None:
        raise HTTPException(status_code=400, detail="cost is required")

    price_per_gallon = cost / gallons if gallons > 0 else None
    record_id = str(uuid.uuid4())

    with get_connection() as conn:
        cur = get_cursor(conn, dict_cursor=not USE_SQLITE)

        # Calculate MPG from previous fill-up odometer reading
        mpg = None
        if mileage and gallons > 0:
            prev_query = adapt_query(
                "SELECT mileage FROM fuel_records WHERE asset_id = %s AND mileage < %s ORDER BY mileage DESC LIMIT 1",
                USE_SQLITE,
            )
            cur.execute(prev_query, (vehicle_id, mileage))
            prev_row = cur.fetchone()
            if prev_row:
                prev_mileage = dict_from_row(prev_row, USE_SQLITE)["mileage"]
                if mileage > prev_mileage:
                    mpg = round((mileage - prev_mileage) / gallons, 1)

        sql = """INSERT INTO fuel_records (id, user_id, asset_id, date, mileage, gallons, cost, price_per_gallon, fuel_type, mpg, notes)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""" if USE_SQLITE else \
              """INSERT INTO fuel_records (id, user_id, asset_id, date, mileage, gallons, cost, price_per_gallon, fuel_type, mpg, notes)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        cur.execute(sql, (
            record_id, token.user_id, vehicle_id, datetime.now(timezone.utc).isoformat(),
            mileage, gallons, cost, price_per_gallon,
            body.get("fuel_type", "regular"), mpg, body.get("notes"),
        ))
        conn.commit()

    return {
        "success": True,
        "result": {
            "record_id": record_id,
            "vehicle_id": vehicle_id,
            "gallons": gallons,
            "cost": cost,
            "mpg": mpg,
            "price_per_gallon": round(price_per_gallon, 3) if price_per_gallon else None,
        },
        "message": f"Logged {gallons:.2f}gal for ${cost:.2f}" + (f" ({mpg} mpg)" if mpg else ""),
    }


@router.post("/agent/log_maintenance")
def agent_log_maintenance(body: dict, token: _TokenData = Depends(require_token)) -> dict:
    vehicle_id = body.get("vehicle_id")
    maintenance_type = body.get("maintenance_type")
    if not vehicle_id:
        raise HTTPException(status_code=400, detail="vehicle_id is required")
    if not maintenance_type:
        raise HTTPException(status_code=400, detail="maintenance_type is required")

    record_id = str(uuid.uuid4())
    with get_connection() as conn:
        cur = get_cursor(conn, dict_cursor=not USE_SQLITE)
        sql = """INSERT INTO maintenance_records (id, user_id, asset_id, maintenance_type, date, cost, description, next_due_date)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""" if USE_SQLITE else \
              """INSERT INTO maintenance_records (id, user_id, asset_id, maintenance_type, date, cost, description, next_due_date)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
        cur.execute(sql, (
            record_id, token.user_id, vehicle_id, maintenance_type,
            str(date.today()), body.get("cost"), body.get("description"),
            body.get("next_due_date"),
        ))
        conn.commit()

    return {
        "success": True,
        "result": {"record_id": record_id, "vehicle_id": vehicle_id, "maintenance_type": maintenance_type},
        "message": f"Logged {maintenance_type}",
    }


@router.post("/agent/get_vehicle_stats")
def agent_get_vehicle_stats(body: dict, token: _TokenData = Depends(require_token)) -> dict:
    vehicle_id = body.get("vehicle_id")
    if not vehicle_id:
        raise HTTPException(status_code=400, detail="vehicle_id is required")

    fuel_rows = _q(
        "SELECT COUNT(*) as fill_ups, SUM(cost) as total_cost, SUM(gallons) as total_gallons, AVG(mpg) as avg_mpg FROM fuel_records WHERE asset_id = %s AND user_id = %s",
        (vehicle_id, token.user_id),
    )
    maint_rows = _q(
        "SELECT COUNT(*) as services, SUM(cost) as total_cost, MAX(date) as last_service FROM maintenance_records WHERE asset_id = %s AND user_id = %s",
        (vehicle_id, token.user_id),
    )

    fr = fuel_rows[0] if fuel_rows else {}
    mr = maint_rows[0] if maint_rows else {}

    return {
        "success": True,
        "result": {
            "vehicle_id": vehicle_id,
            "fuel": {
                "fill_ups": int(fr.get("fill_ups") or 0),
                "total_cost": round(float(fr.get("total_cost") or 0), 2),
                "total_gallons": round(float(fr.get("total_gallons") or 0), 2),
                "avg_mpg": round(float(fr.get("avg_mpg") or 0), 1),
            },
            "maintenance": {
                "services": int(mr.get("services") or 0),
                "total_cost": round(float(mr.get("total_cost") or 0), 2),
                "last_service": str(mr.get("last_service") or ""),
            },
        },
    }


# ---------------------------------------------------------------------------
# Cross-module data
# ---------------------------------------------------------------------------

@router.get("/data/{data_id}")
def get_shared_data(data_id: str, token: _TokenData = Depends(require_token)) -> dict:
    if data_id == "fuel_costs":
        rows = _q(
            "SELECT SUM(cost) as total_cost, SUM(gallons) as total_gallons, AVG(mpg) as avg_mpg FROM fuel_records WHERE user_id = %s",
            (token.user_id,),
        )
        r = rows[0] if rows else {}
        return {
            "data_id": "fuel_costs",
            "data": {
                "total_cost": round(float(r.get("total_cost") or 0), 2),
                "total_gallons": round(float(r.get("total_gallons") or 0), 2),
                "avg_mpg": round(float(r.get("avg_mpg") or 0), 1),
            },
        }

    if data_id == "maintenance_costs":
        rows = _q(
            "SELECT COUNT(*) as services, SUM(cost) as total_cost FROM maintenance_records WHERE user_id = %s",
            (token.user_id,),
        )
        r = rows[0] if rows else {}
        return {
            "data_id": "maintenance_costs",
            "data": {
                "total_cost": round(float(r.get("total_cost") or 0), 2),
                "service_count": int(r.get("services") or 0),
            },
        }

    raise HTTPException(status_code=404, detail=f"Unknown data_id: {data_id}")
