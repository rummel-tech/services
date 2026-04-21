"""
Pytest configuration for meal-planner tests.
"""

import os
import sqlite3
import sys
import tempfile
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add paths for imports
test_file = Path(__file__).resolve()
service_root = test_file.parents[1]
services_root = test_file.parents[2]

sys.path.insert(0, str(service_root))
sys.path.insert(0, str(services_root))

# Disable Prometheus metrics in tests to prevent "Duplicated timeseries" errors
# when multiple test modules both import the app.
os.environ["ENABLE_METRICS"] = "false"


def _setup_db(path: str) -> None:
    """Create schema and seed test data."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS meals (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            meal_type TEXT NOT NULL,
            date TEXT NOT NULL,
            calories INTEGER,
            protein_g INTEGER,
            carbs_g INTEGER,
            fat_g INTEGER,
            notes TEXT
        );
    """)

    # Fixed historical date used in tests: 2025-12-01 (Monday)
    conn.execute(
        "INSERT INTO meals (id, user_id, name, meal_type, date, calories, protein_g, carbs_g, fat_g) "
        "VALUES (?, 'user-123', 'Oatmeal', 'breakfast', '2025-12-01', 350, 12, 60, 5)",
        (str(uuid.uuid4()),),
    )
    conn.execute(
        "INSERT INTO meals (id, user_id, name, meal_type, date, calories, protein_g, carbs_g, fat_g) "
        "VALUES (?, 'user-123', 'Grilled Chicken', 'lunch', '2025-12-03', 480, 45, 20, 12)",
        (str(uuid.uuid4()),),
    )

    # Seed one meal per day for the current week (Monday–Sunday)
    today = date.today()
    week_monday = today - timedelta(days=today.weekday())
    for offset in range(7):
        day = week_monday + timedelta(days=offset)
        conn.execute(
            "INSERT INTO meals (id, user_id, name, meal_type, date, calories, protein_g, carbs_g, fat_g) "
            "VALUES (?, 'user-123', 'Weekly Meal', 'lunch', ?, 500, 30, 60, 15)",
            (str(uuid.uuid4()), day.isoformat()),
        )

    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def client():
    """Test client with SQLite DB, seeded data, and mocked auth."""
    tmp = tempfile.mktemp(suffix=".db")
    _setup_db(tmp)
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp}"

    # Clear cached modules so the new DATABASE_URL is picked up
    for mod in list(sys.modules.keys()):
        if mod in ("main", "routers.artemis", "routers.auth"):
            del sys.modules[mod]

    from main import app
    from routers.auth import require_token, TokenData

    async def _mock_auth():
        return TokenData(user_id="user-123", email="test@test.local")

    app.dependency_overrides[require_token] = _mock_auth

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    os.unlink(tmp)
