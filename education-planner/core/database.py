"""Database connection management — PostgreSQL with SQLite fallback for development."""

import os
import sqlite3
import logging
import threading
from contextlib import contextmanager

from core.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
DATABASE_URL = settings.database_url
USE_SQLITE = DATABASE_URL.startswith('sqlite')

if not USE_SQLITE:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from psycopg2 import pool as pg_pool
    except ImportError:
        USE_SQLITE = True
        DATABASE_URL = 'sqlite:///education_dev.db'
        logger.warning('psycopg2 not available, falling back to SQLite')

_pg_pool = None
_sqlite_initialized = False
_init_lock = threading.Lock()

_SCHEMA = """
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

    CREATE TABLE IF NOT EXISTS registration_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        is_used BOOLEAN DEFAULT 0,
        used_by_user_id TEXT,
        expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS waitlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS education_goals (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        category TEXT NOT NULL DEFAULT 'personal',
        target_date TEXT,
        is_completed BOOLEAN NOT NULL DEFAULT 0,
        completed_at TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        deleted_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_goals_user_id ON education_goals(user_id);
    CREATE INDEX IF NOT EXISTS idx_goals_completed ON education_goals(is_completed);
    CREATE INDEX IF NOT EXISTS idx_goals_active ON education_goals(user_id, deleted_at);

    CREATE TABLE IF NOT EXISTS weekly_plans (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        week_start_date TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, week_start_date)
    );

    CREATE INDEX IF NOT EXISTS idx_plans_user_id ON weekly_plans(user_id);
    CREATE INDEX IF NOT EXISTS idx_plans_week_start ON weekly_plans(week_start_date);

    CREATE TABLE IF NOT EXISTS activities (
        id TEXT PRIMARY KEY,
        plan_id TEXT NOT NULL,
        goal_id TEXT,
        title TEXT NOT NULL,
        description TEXT,
        duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0),
        actual_minutes INTEGER,
        scheduled_time TEXT NOT NULL,
        is_completed BOOLEAN NOT NULL DEFAULT 0,
        completed_at TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (plan_id) REFERENCES weekly_plans(id) ON DELETE CASCADE,
        FOREIGN KEY (goal_id) REFERENCES education_goals(id) ON DELETE SET NULL
    );

    CREATE INDEX IF NOT EXISTS idx_activities_plan_id ON activities(plan_id);
    CREATE INDEX IF NOT EXISTS idx_activities_goal_id ON activities(goal_id);
    CREATE INDEX IF NOT EXISTS idx_activities_scheduled ON activities(scheduled_time);
"""


def init_pg_pool() -> None:
    global _pg_pool
    if not USE_SQLITE and _pg_pool is None:
        _pg_pool = psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DATABASE_URL)
        logger.info('PostgreSQL connection pool initialised')
    elif USE_SQLITE:
        _init_sqlite()


def close_pg_pool() -> None:
    global _pg_pool
    if _pg_pool:
        _pg_pool.closeall()
        _pg_pool = None


def _init_sqlite() -> None:
    global _sqlite_initialized
    with _init_lock:
        if _sqlite_initialized:
            return
        db_path = DATABASE_URL.replace('sqlite:///', '')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        conn.commit()
        conn.close()
        _sqlite_initialized = True
        logger.info('SQLite database initialised')


@contextmanager
def get_db():
    """Context manager that yields a database connection."""
    if USE_SQLITE:
        db_path = DATABASE_URL.replace('sqlite:///', '')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        try:
            yield conn
        finally:
            conn.close()
    else:
        conn = _pg_pool.getconn()
        try:
            yield conn
        finally:
            _pg_pool.putconn(conn)


def get_cursor(conn):
    """Return the appropriate cursor type for the current DB backend."""
    if USE_SQLITE:
        return conn.cursor()
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# Initialise SQLite on import when running in dev mode
if USE_SQLITE:
    _init_sqlite()
