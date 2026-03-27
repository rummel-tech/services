"""Database setup for the auth service. SQLite in dev, Postgres in prod."""
import sqlite3
import threading
from contextlib import contextmanager

from auth.core.settings import get_settings

_settings = get_settings()
DATABASE_URL = _settings.database_url
USE_SQLITE = DATABASE_URL.startswith("sqlite")

if not USE_SQLITE:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from psycopg2 import pool as pg_pool
    except ImportError:
        USE_SQLITE = True
        DATABASE_URL = "sqlite:///auth_dev.db"

_pg_pool = None
_pg_init_lock = threading.Lock()
_pg_initialized = False

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT,
    full_name TEXT,
    google_id TEXT UNIQUE,
    is_active INTEGER DEFAULT 1,
    is_admin INTEGER DEFAULT 0,
    enabled_modules TEXT DEFAULT '[]',
    permissions TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
"""

PG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT,
    full_name TEXT,
    google_id TEXT UNIQUE,
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    enabled_modules TEXT DEFAULT '[]',
    permissions TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
"""


def _init_sqlite() -> None:
    db_path = DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


def _init_pg_pool() -> None:
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = pg_pool.SimpleConnectionPool(1, 10, dsn=DATABASE_URL)


def _init_postgres() -> None:
    global _pg_initialized
    if _pg_initialized:
        return
    with _pg_init_lock:
        if _pg_initialized:
            return
        conn = _pg_pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(PG_SCHEMA_SQL)
            conn.commit()
            cur.close()
            _pg_initialized = True
        finally:
            _pg_pool.putconn(conn)


def init_db() -> None:
    if USE_SQLITE:
        _init_sqlite()
    else:
        _init_pg_pool()
        _init_postgres()


def close_db() -> None:
    global _pg_pool
    if _pg_pool:
        _pg_pool.closeall()
        _pg_pool = None


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
    return conn.cursor(cursor_factory=RealDictCursor)
