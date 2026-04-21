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
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_meals_user_id ON meals(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_meals_date ON meals(date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_meals_type ON meals(meal_type)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS weekly_meal_plans (
            id UUID PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            week_start DATE NOT NULL,
            focus VARCHAR(100) DEFAULT 'balanced',
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_weekly_plans_user_id ON weekly_meal_plans(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_weekly_plans_week ON weekly_meal_plans(week_start)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS weekly_meal_plans")
    op.execute("DROP TABLE IF EXISTS meals")
