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
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            full_name TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            is_admin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS registration_codes (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            is_used BOOLEAN DEFAULT FALSE,
            used_by_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS waitlist (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    op.execute("""
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
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_goals_user_id ON education_goals(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_goals_completed ON education_goals(is_completed)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_goals_active ON education_goals(user_id, deleted_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS weekly_plans (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            week_start_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, week_start_date)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_plans_user_id ON weekly_plans(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_plans_week_start ON weekly_plans(week_start_date)")

    op.execute("""
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
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_activities_plan_id ON activities(plan_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_activities_goal_id ON activities(goal_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_activities_scheduled ON activities(scheduled_time)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS activities")
    op.execute("DROP TABLE IF EXISTS weekly_plans")
    op.execute("DROP TABLE IF EXISTS education_goals")
    op.execute("DROP TABLE IF EXISTS waitlist")
    op.execute("DROP TABLE IF EXISTS registration_codes")
    op.execute("DROP TABLE IF EXISTS users")
