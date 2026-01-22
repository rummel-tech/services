"""initial_schema

Revision ID: 561152f2b473
Revises:
Create Date: 2026-01-22 12:12:12.078772

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '561152f2b473'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - create all initial tables."""

    # Users table
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            full_name TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            is_admin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Registration codes table
    op.execute("""
        CREATE TABLE IF NOT EXISTS registration_codes (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            is_used BOOLEAN DEFAULT FALSE,
            used_by_user_id TEXT,
            expires_at TIMESTAMP,
            distributed_to TEXT,
            distributed_at TIMESTAMP,
            distributed_by_user_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Waitlist table
    op.execute("""
        CREATE TABLE IF NOT EXISTS waitlist (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # User goals table
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_goals (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            goal_type TEXT NOT NULL,
            target_value REAL,
            target_unit TEXT,
            target_date TEXT,
            notes TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Goal plans table
    op.execute("""
        CREATE TABLE IF NOT EXISTS goal_plans (
            id SERIAL PRIMARY KEY,
            goal_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Health samples table
    op.execute("""
        CREATE TABLE IF NOT EXISTS health_samples (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            sample_type TEXT NOT NULL,
            value REAL,
            unit TEXT,
            start_time TEXT,
            end_time TEXT,
            source_app TEXT,
            source_uuid TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Health metrics table
    op.execute("""
        CREATE TABLE IF NOT EXISTS health_metrics (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            hrv_ms REAL,
            resting_hr INTEGER,
            vo2max REAL,
            sleep_hours REAL,
            weight_kg REAL,
            rpe INTEGER,
            soreness INTEGER,
            mood INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date)
        )
    """)

    # Chat sessions table
    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Chat messages table
    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            session_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Weekly plans table
    op.execute("""
        CREATE TABLE IF NOT EXISTS weekly_plans (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            week_start TEXT NOT NULL,
            focus TEXT,
            plan_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Daily plans table
    op.execute("""
        CREATE TABLE IF NOT EXISTS daily_plans (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            plan_json TEXT,
            status TEXT DEFAULT 'pending',
            ai_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Workouts table
    op.execute("""
        CREATE TABLE IF NOT EXISTS workouts (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            warmup TEXT,
            main TEXT,
            cooldown TEXT,
            notes TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Strength metrics table
    op.execute("""
        CREATE TABLE IF NOT EXISTS strength_metrics (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            lift TEXT NOT NULL,
            weight REAL NOT NULL,
            reps INTEGER NOT NULL,
            set_number INTEGER NOT NULL,
            estimated_1rm REAL,
            velocity_m_per_s REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date, lift, set_number)
        )
    """)

    # Swim metrics table
    op.execute("""
        CREATE TABLE IF NOT EXISTS swim_metrics (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            distance_meters REAL NOT NULL,
            duration_seconds INTEGER NOT NULL,
            avg_pace_seconds REAL NOT NULL,
            water_type TEXT NOT NULL,
            stroke_rate REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_goal_plans_goal_id ON goal_plans(goal_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_goal_plans_user_id ON goal_plans(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_weekly_plans_user_id ON weekly_plans(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_health_samples_user_id ON health_samples(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_health_samples_type_time ON health_samples(sample_type, start_time)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_health_samples_dedupe ON health_samples(user_id, sample_type, start_time, source_uuid)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_plans_user_id ON daily_plans(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_workouts_user_id ON workouts(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_workouts_user_type ON workouts(user_id, type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_strength_metrics_user_id ON strength_metrics(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_strength_metrics_user_lift ON strength_metrics(user_id, lift)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_strength_metrics_user_date ON strength_metrics(user_id, date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_swim_metrics_user_id ON swim_metrics(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_swim_metrics_user_date ON swim_metrics(user_id, date)")

    # Optimized composite indexes for frequent queries
    op.execute("CREATE INDEX IF NOT EXISTS idx_health_samples_user_type_time ON health_samples(user_id, sample_type, start_time)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_plans_user_date ON daily_plans(user_id, date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_weekly_plans_user_week ON weekly_plans(user_id, week_start)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created ON chat_messages(session_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_goals_user_active ON user_goals(user_id, is_active)")


def downgrade() -> None:
    """Downgrade schema - drop all tables."""

    # Drop tables in reverse order (respecting dependencies)
    op.execute("DROP TABLE IF EXISTS swim_metrics CASCADE")
    op.execute("DROP TABLE IF EXISTS strength_metrics CASCADE")
    op.execute("DROP TABLE IF EXISTS workouts CASCADE")
    op.execute("DROP TABLE IF EXISTS daily_plans CASCADE")
    op.execute("DROP TABLE IF EXISTS weekly_plans CASCADE")
    op.execute("DROP TABLE IF EXISTS chat_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS chat_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS health_metrics CASCADE")
    op.execute("DROP TABLE IF EXISTS health_samples CASCADE")
    op.execute("DROP TABLE IF EXISTS goal_plans CASCADE")
    op.execute("DROP TABLE IF EXISTS user_goals CASCADE")
    op.execute("DROP TABLE IF EXISTS waitlist CASCADE")
    op.execute("DROP TABLE IF EXISTS registration_codes CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
