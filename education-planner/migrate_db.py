"""
Database migration script for education-planner service.

Creates all necessary tables for learning goal tracking and weekly planning.
"""

import sys
from pathlib import Path

# Add parent directory to path for common imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.database import DatabaseManager, get_database_url


def create_tables():
    """Create all tables for education-planner service."""

    db_manager = DatabaseManager()

    print(f"Creating tables for database: {get_database_url()}")

    users_sql = """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        full_name TEXT,
        is_active BOOLEAN DEFAULT TRUE,
        is_admin BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """

    registration_codes_sql = """
    CREATE TABLE IF NOT EXISTS registration_codes (
        id SERIAL PRIMARY KEY,
        code TEXT UNIQUE NOT NULL,
        is_used BOOLEAN DEFAULT FALSE,
        used_by_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
        expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """

    waitlist_sql = """
    CREATE TABLE IF NOT EXISTS waitlist (
        id SERIAL PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """

    education_goals_sql = """
    CREATE TABLE IF NOT EXISTS education_goals (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        category TEXT NOT NULL DEFAULT 'personal',
        target_date TEXT,
        is_completed BOOLEAN NOT NULL DEFAULT FALSE,
        completed_at TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        deleted_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_goals_user_id ON education_goals(user_id);
    CREATE INDEX IF NOT EXISTS idx_goals_completed ON education_goals(is_completed);
    CREATE INDEX IF NOT EXISTS idx_goals_active ON education_goals(user_id, deleted_at);
    """

    weekly_plans_sql = """
    CREATE TABLE IF NOT EXISTS weekly_plans (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        week_start_date TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(user_id, week_start_date)
    );

    CREATE INDEX IF NOT EXISTS idx_plans_user_id ON weekly_plans(user_id);
    CREATE INDEX IF NOT EXISTS idx_plans_week_start ON weekly_plans(week_start_date);
    """

    activities_sql = """
    CREATE TABLE IF NOT EXISTS activities (
        id TEXT PRIMARY KEY,
        plan_id TEXT NOT NULL REFERENCES weekly_plans(id) ON DELETE CASCADE,
        goal_id TEXT REFERENCES education_goals(id) ON DELETE SET NULL,
        title TEXT NOT NULL,
        description TEXT,
        duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
        actual_minutes INTEGER,
        scheduled_time TEXT NOT NULL,
        is_completed BOOLEAN NOT NULL DEFAULT FALSE,
        completed_at TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_activities_plan_id ON activities(plan_id);
    CREATE INDEX IF NOT EXISTS idx_activities_goal_id ON activities(goal_id);
    CREATE INDEX IF NOT EXISTS idx_activities_scheduled ON activities(scheduled_time);
    """

    tables = [
        ("users", users_sql),
        ("registration_codes", registration_codes_sql),
        ("waitlist", waitlist_sql),
        ("education_goals", education_goals_sql),
        ("weekly_plans", weekly_plans_sql),
        ("activities", activities_sql),
    ]

    for table_name, sql in tables:
        try:
            print(f"Creating table: {table_name}")
            db_manager.execute_migration(sql)
            print(f"✓ {table_name} created successfully")
        except Exception as e:
            print(f"✗ Error creating {table_name}: {e}")

    print("\nDatabase migration completed!")


if __name__ == "__main__":
    create_tables()
