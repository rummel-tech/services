"""
Database migration script for meal-planner service.

Creates all necessary tables for nutrition tracking.
"""

import sys
from pathlib import Path

# Add parent directory to path for common imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.database import DatabaseManager, get_database_url


def create_tables():
    """Create all tables for meal-planner service."""

    db_manager = DatabaseManager()

    print(f"Creating tables for database: {get_database_url()}")

    # Meal items table
    meals_sql = """
    CREATE TABLE IF NOT EXISTS meals (
        id UUID PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        name VARCHAR(255) NOT NULL,
        meal_type VARCHAR(50) NOT NULL,
        date DATE NOT NULL,
        calories INTEGER,
        protein_g INTEGER,
        carbs_g INTEGER,
        fat_g INTEGER,
        notes TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_meals_user_id ON meals(user_id);
    CREATE INDEX IF NOT EXISTS idx_meals_date ON meals(date);
    CREATE INDEX IF NOT EXISTS idx_meals_type ON meals(meal_type);
    """

    # Weekly meal plans
    weekly_plans_sql = """
    CREATE TABLE IF NOT EXISTS weekly_meal_plans (
        id UUID PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        week_start DATE NOT NULL,
        focus VARCHAR(100) DEFAULT 'balanced',
        notes TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_weekly_plans_user_id ON weekly_meal_plans(user_id);
    CREATE INDEX IF NOT EXISTS idx_weekly_plans_week ON weekly_meal_plans(week_start);
    """

    # Execute all migrations
    tables = [
        ("meals", meals_sql),
        ("weekly_meal_plans", weekly_plans_sql),
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
