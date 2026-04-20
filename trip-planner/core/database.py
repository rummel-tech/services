import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.database import (
    get_database_url,
    is_sqlite,
    get_connection,
    get_cursor,
    adapt_query,
    dict_from_row,
    init_connection_pool,
    close_connection_pool,
)

logger = logging.getLogger(__name__)

DATABASE_URL = get_database_url() or "sqlite:///trip_dev.db"
USE_SQLITE = is_sqlite(DATABASE_URL)

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS trips (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    destination TEXT NOT NULL,
    trip_type TEXT NOT NULL DEFAULT 'vacation',
    start_date TEXT,
    end_date TEXT,
    budget_cents INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'planning',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS itinerary_items (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL,
    day_date TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    start_time TEXT,
    end_time TEXT,
    category TEXT NOT NULL DEFAULT 'activity',
    notes TEXT,
    cost_cents INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS packing_items (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    name TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    packed INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS trip_expenses (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'misc',
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL DEFAULT 0,
    expense_date TEXT NOT NULL,
    added_at TEXT NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
);
"""


def init_db():
    with get_connection() as conn:
        cur = get_cursor(conn)
        for statement in CREATE_TABLES.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                cur.execute(stmt)
        conn.commit()
    logger.info("Trip Planner DB initialized (USE_SQLITE=%s)", USE_SQLITE)


def init_pg_pool():
    init_connection_pool(DATABASE_URL)


def close_pg_pool():
    close_connection_pool()
