"""
Pytest configuration for vehicle-manager tests.
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add paths for imports
test_file = Path(__file__).resolve()
service_root = test_file.parents[1]
services_root = test_file.parents[2]

sys.path.insert(0, str(service_root))
sys.path.insert(0, str(services_root))


def _setup_db(path: str) -> None:
    """Create schema and seed minimal test data."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            asset_type TEXT NOT NULL DEFAULT 'vehicle',
            category TEXT,
            manufacturer TEXT,
            model_number TEXT,
            serial_number TEXT,
            purchase_date TEXT,
            purchase_price REAL,
            condition TEXT DEFAULT 'good',
            location TEXT,
            notes TEXT,
            context TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS maintenance_records (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            maintenance_type TEXT NOT NULL,
            date TEXT NOT NULL,
            cost REAL,
            description TEXT,
            performed_by TEXT,
            next_due_date TEXT,
            next_due_mileage INTEGER,
            notes TEXT,
            context TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS fuel_records (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            date TEXT NOT NULL,
            mileage INTEGER NOT NULL,
            gallons REAL NOT NULL,
            cost REAL NOT NULL,
            price_per_gallon REAL,
            fuel_type TEXT DEFAULT 'regular',
            mpg REAL,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def client():
    """Test client with SQLite DB and mocked auth."""
    tmp = tempfile.mktemp(suffix=".db")
    _setup_db(tmp)
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp}"

    from main import app  # noqa: PLC0415
    from routers.auth import require_token, TokenData  # noqa: PLC0415

    async def _mock_auth():
        return TokenData(user_id="user-123", email="test@test.local")

    app.dependency_overrides[require_token] = _mock_auth

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    os.unlink(tmp)
