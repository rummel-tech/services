import os
import sqlite3
import logging
from contextlib import contextmanager
from core.settings import get_settings
import threading

logger = logging.getLogger(__name__)
settings = get_settings()
DATABASE_URL = settings.database_url
USE_SQLITE = DATABASE_URL.startswith("sqlite")

if not USE_SQLITE:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from psycopg2 import pool
    except ImportError:
        USE_SQLITE = True
        DATABASE_URL = "sqlite:///fitness_dev.db"
        logger.warning("psycopg2 not available, falling back to SQLite")

_pg_pool = None
_pg_init_lock = threading.Lock()
_pg_initialized = False

def init_pg_pool():
    global _pg_pool
    if not USE_SQLITE and _pg_pool is None:
        _pg_pool = psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DATABASE_URL)

def close_pg_pool():
    global _pg_pool
    if _pg_pool:
        _pg_pool.closeall()

# Initialize SQLite database with schema
def init_sqlite():
    db_path = DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Create tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            goal_type TEXT NOT NULL,
            target_value REAL,
            target_unit TEXT,
            target_date TEXT,
            notes TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS goal_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (goal_id) REFERENCES user_goals(id)
        );

        CREATE TABLE IF NOT EXISTS health_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            sample_type TEXT NOT NULL,
            value REAL,
            unit TEXT,
            start_time TEXT,
            end_time TEXT,
            source_app TEXT,
            source_uuid TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS health_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );

        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            full_name TEXT,
            is_active BOOLEAN DEFAULT 1,
            is_admin BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS weekly_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            week_start TEXT NOT NULL,
            focus TEXT,
            plan_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, week_start)
        );

        CREATE TABLE IF NOT EXISTS daily_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            plan_json TEXT,
            status TEXT DEFAULT 'pending',
            ai_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date)
        );

        CREATE TABLE IF NOT EXISTS registration_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            is_used BOOLEAN DEFAULT 0,
            used_by_user_id TEXT,
            expires_at TIMESTAMP,
            distributed_to TEXT,
            distributed_at TIMESTAMP,
            distributed_by_user_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS waitlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );

        -- Basic indexes
        CREATE INDEX IF NOT EXISTS idx_goal_plans_goal_id ON goal_plans(goal_id);
        CREATE INDEX IF NOT EXISTS idx_goal_plans_user_id ON goal_plans(user_id);
        CREATE INDEX IF NOT EXISTS idx_weekly_plans_user_id ON weekly_plans(user_id);
        CREATE INDEX IF NOT EXISTS idx_health_samples_user_id ON health_samples(user_id);
        CREATE INDEX IF NOT EXISTS idx_health_samples_type_time ON health_samples(sample_type, start_time);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_health_samples_dedupe ON health_samples(user_id, sample_type, start_time, source_uuid);
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id);
        CREATE INDEX IF NOT EXISTS idx_daily_plans_user_id ON daily_plans(user_id);
        CREATE INDEX IF NOT EXISTS idx_workouts_user_id ON workouts(user_id);
        CREATE INDEX IF NOT EXISTS idx_workouts_user_type ON workouts(user_id, type);

        -- Optimized composite indexes for frequent queries
        CREATE INDEX IF NOT EXISTS idx_health_samples_user_type_time ON health_samples(user_id, sample_type, start_time);
        CREATE INDEX IF NOT EXISTS idx_daily_plans_user_date ON daily_plans(user_id, date);
        CREATE INDEX IF NOT EXISTS idx_weekly_plans_user_week ON weekly_plans(user_id, week_start);
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created ON chat_messages(session_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_user_goals_user_active ON user_goals(user_id, is_active);
    """)
    # Migration: add target_unit if missing
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(user_goals)")
    cols = [r[1] for r in cur.fetchall()]
    if 'target_unit' not in cols:
        cur.execute("ALTER TABLE user_goals ADD COLUMN target_unit TEXT")
    # Future migrations for health_samples could be added here
    # Add source_uuid column if missing (dedup support)
    cur.execute("PRAGMA table_info(health_samples)")
    hcols = [r[1] for r in cur.fetchall()]
    if 'source_uuid' not in hcols:
        cur.execute("ALTER TABLE health_samples ADD COLUMN source_uuid TEXT")
        # Recreate unique index (safe if existing) after adding column
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_health_samples_dedupe ON health_samples(user_id, sample_type, start_time, source_uuid)")
    # Add is_admin column if missing
    cur.execute("PRAGMA table_info(users)")
    user_cols = [r[1] for r in cur.fetchall()]
    if 'is_admin' not in user_cols:
        cur.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0")
    # Add expires_at column to registration_codes if missing
    cur.execute("PRAGMA table_info(registration_codes)")
    code_cols = [r[1] for r in cur.fetchall()]
    if 'expires_at' not in code_cols:
        cur.execute("ALTER TABLE registration_codes ADD COLUMN expires_at TIMESTAMP")
    if 'distributed_to' not in code_cols:
        cur.execute("ALTER TABLE registration_codes ADD COLUMN distributed_to TEXT")
    if 'distributed_at' not in code_cols:
        cur.execute("ALTER TABLE registration_codes ADD COLUMN distributed_at TIMESTAMP")
    if 'distributed_by_user_id' not in code_cols:
        cur.execute("ALTER TABLE registration_codes ADD COLUMN distributed_by_user_id TEXT")
    conn.commit()
    conn.close()

def init_postgres():
    global _pg_initialized
    if _pg_initialized:
        return
    with _pg_init_lock:
        if _pg_initialized:
            return
        try:
            conn = _pg_pool.getconn()
            cur = conn.cursor()
            # Create tables (id SERIAL for autoincrement). Use IF NOT EXISTS to be idempotent.
            cur.execute("""
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
                );
                CREATE TABLE IF NOT EXISTS goal_plans (
                    id SERIAL PRIMARY KEY,
                    goal_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
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
                );
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
                );
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    full_name TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS weekly_plans (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    week_start TEXT NOT NULL,
                    focus TEXT,
                    plan_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS daily_plans (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    plan_json TEXT,
                    status TEXT DEFAULT 'pending',
                    ai_notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
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
                );
                CREATE TABLE IF NOT EXISTS waitlist (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
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
                );
                CREATE INDEX IF NOT EXISTS idx_goal_plans_goal_id ON goal_plans(goal_id);
                CREATE INDEX IF NOT EXISTS idx_goal_plans_user_id ON goal_plans(user_id);
                CREATE INDEX IF NOT EXISTS idx_weekly_plans_user_id ON weekly_plans(user_id);
                CREATE INDEX IF NOT EXISTS idx_health_samples_user_id ON health_samples(user_id);
                CREATE INDEX IF NOT EXISTS idx_health_samples_type_time ON health_samples(sample_type, start_time);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_health_samples_dedupe ON health_samples(user_id, sample_type, start_time, source_uuid);
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id);
                CREATE INDEX IF NOT EXISTS idx_daily_plans_user_id ON daily_plans(user_id);
                CREATE INDEX IF NOT EXISTS idx_workouts_user_id ON workouts(user_id);
                CREATE INDEX IF NOT EXISTS idx_workouts_user_type ON workouts(user_id, type);
            """)
            conn.commit()
            cur.close()
            _pg_pool.putconn(conn)
            _pg_initialized = True
        except Exception as e:
            logger.error(f"Postgres initialization failed: {e}")

if USE_SQLITE:
    init_sqlite()
else:
    init_pg_pool()
    init_postgres()

@contextmanager
def get_db():
    if USE_SQLITE:
        db_path = DATABASE_URL.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = _pg_pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            _pg_pool.putconn(conn)

def get_cursor(conn):
    if USE_SQLITE:
        return conn.cursor()
    else:
        return conn.cursor(cursor_factory=RealDictCursor)
