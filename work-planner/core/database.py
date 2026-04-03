"""Database connection management — PostgreSQL with SQLite fallback for development."""

import os
import re
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
        DATABASE_URL = 'sqlite:///work_dev.db'
        logger.warning('psycopg2 not available, falling back to SQLite')

_pg_pool = None
_sqlite_initialized = False
_init_lock = threading.Lock()


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
        conn.executescript("""
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

            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                goal_type TEXT NOT NULL DEFAULT 'corporate',
                status TEXT NOT NULL DEFAULT 'notStarted',
                target_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_goals_user_id ON goals(user_id);

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_plans_user_id ON plans(user_id);
            CREATE INDEX IF NOT EXISTS idx_plans_goal_id ON plans(goal_id);

            CREATE TABLE IF NOT EXISTS day_planners (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, date)
            );

            CREATE INDEX IF NOT EXISTS idx_day_planners_user_date ON day_planners(user_id, date);

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                day_planner_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                priority TEXT NOT NULL DEFAULT 'medium',
                scheduled_time TEXT,
                duration_minutes INTEGER,
                completed BOOLEAN DEFAULT 0,
                plan_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (day_planner_id) REFERENCES day_planners(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_day_planner ON tasks(day_planner_id);

            CREATE TABLE IF NOT EXISTS week_planners (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                week_start_date TEXT NOT NULL,
                weekly_goals TEXT DEFAULT '[]',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, week_start_date)
            );

            CREATE INDEX IF NOT EXISTS idx_week_planners_user ON week_planners(user_id, week_start_date);
        """)
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


class _QueryAdapterCursor:
    """Cursor wrapper that translates SQLite-style ? placeholders to %s for PostgreSQL."""

    # Matches single-quoted string literals OR a bare ? placeholder.
    # The replacement callback leaves string literals unchanged and converts ? to %s.
    _PLACEHOLDER_RE = re.compile(r"'[^']*'|(\?)")

    def __init__(self, cursor, use_sqlite: bool):
        self._cur = cursor
        self._use_sqlite = use_sqlite

    @classmethod
    def _adapt(cls, query: str) -> str:
        """Replace ? placeholders with %s, leaving ? inside string literals intact."""
        def _replace(m: re.Match) -> str:
            return '%s' if m.group(1) is not None else m.group(0)
        return cls._PLACEHOLDER_RE.sub(_replace, query)

    def execute(self, query: str, params=None):
        if not self._use_sqlite:
            query = self._adapt(query)
        if params is not None:
            self._cur.execute(query, params)
        else:
            self._cur.execute(query)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __getattr__(self, name):
        return getattr(self._cur, name)


def get_cursor(conn) -> _QueryAdapterCursor:
    """Return the appropriate cursor type for the current DB backend."""
    if USE_SQLITE:
        return _QueryAdapterCursor(conn.cursor(), use_sqlite=True)
    return _QueryAdapterCursor(conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor), use_sqlite=False)


# Initialise SQLite on import when running in dev mode
if USE_SQLITE:
    _init_sqlite()
