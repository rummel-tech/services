"""Initial schema.

Revision ID: 0001
Revises:
Create Date: 2026-04-20
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
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
        )
    """)

    op.execute("""
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
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS packing_items (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            packed INTEGER NOT NULL DEFAULT 0,
            added_at TEXT NOT NULL,
            FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS trip_expenses (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'misc',
            description TEXT NOT NULL,
            amount_cents INTEGER NOT NULL DEFAULT 0,
            expense_date TEXT NOT NULL,
            added_at TEXT NOT NULL,
            FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS trip_expenses")
    op.execute("DROP TABLE IF EXISTS packing_items")
    op.execute("DROP TABLE IF EXISTS itinerary_items")
    op.execute("DROP TABLE IF EXISTS trips")
