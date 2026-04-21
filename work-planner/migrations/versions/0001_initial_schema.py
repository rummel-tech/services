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
            used_by_user_id TEXT,
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
        CREATE TABLE IF NOT EXISTS goals (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            goal_type TEXT NOT NULL DEFAULT 'corporate',
            status TEXT NOT NULL DEFAULT 'notStarted',
            target_date TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_goals_user_id ON goals(user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            goal_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            start_date TEXT,
            end_date TEXT,
            steps TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_plans_user_id ON plans(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_plans_goal_id ON plans(goal_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS day_planners (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, date)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_day_planners_user_date ON day_planners(user_id, date)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            day_planner_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            priority TEXT NOT NULL DEFAULT 'medium',
            scheduled_time TEXT,
            duration_minutes INTEGER,
            completed BOOLEAN DEFAULT FALSE,
            plan_id TEXT,
            pomodoro_block INTEGER,
            task_category TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (day_planner_id) REFERENCES day_planners(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_day_planner ON tasks(day_planner_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS week_planners (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            week_start_date TEXT NOT NULL,
            weekly_goals TEXT DEFAULT '[]',
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, week_start_date)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_week_planners_user ON week_planners(user_id, week_start_date)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS week_planners")
    op.execute("DROP TABLE IF EXISTS tasks")
    op.execute("DROP TABLE IF EXISTS day_planners")
    op.execute("DROP TABLE IF EXISTS plans")
    op.execute("DROP TABLE IF EXISTS goals")
    op.execute("DROP TABLE IF EXISTS waitlist")
    op.execute("DROP TABLE IF EXISTS registration_codes")
    op.execute("DROP TABLE IF EXISTS users")
