"""
Pytest configuration for home-manager tests.
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
os.environ.setdefault("ENABLE_METRICS", "false")
sys.path.insert(0, str(services_root))


def _setup_db(path: str) -> None:
    """Create schema and seed minimal test data."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'open',
            priority TEXT DEFAULT 'medium',
            category TEXT,
            due_date TEXT,
            completed_at TEXT,
            estimated_minutes INTEGER,
            tags TEXT,
            context TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS goals (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT,
            target_value REAL,
            target_unit TEXT,
            target_date TEXT,
            notes TEXT,
            context TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            asset_type TEXT NOT NULL,
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
    """)
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def client():
    """Test client with SQLite DB and mocked auth."""
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
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
