"""
Common database utilities for all services.

Provides:
- Connection pooling
- Context managers
- Query helpers
- Migration support
"""

import os
from typing import Optional, Any, Dict
from contextlib import contextmanager
from urllib.parse import urlparse
import asyncpg
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool


# Global connection pools
_pg_pool: Optional[SimpleConnectionPool] = None
_async_pool: Optional[asyncpg.Pool] = None


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv("DATABASE_URL", "sqlite:///app.db")


def is_postgres(database_url: Optional[str] = None) -> bool:
    """Check if database is PostgreSQL."""
    db_url = database_url or get_database_url()
    return db_url.startswith("postgresql://") or db_url.startswith("postgres://")


def is_sqlite(database_url: Optional[str] = None) -> bool:
    """Check if database is SQLite."""
    db_url = database_url or get_database_url()
    return db_url.startswith("sqlite://")


def init_connection_pool(
    database_url: Optional[str] = None,
    min_connections: int = 1,
    max_connections: int = 10
) -> None:
    """
    Initialize PostgreSQL connection pool.

    Args:
        database_url: Database URL (uses DATABASE_URL env var if not provided)
        min_connections: Minimum pool size
        max_connections: Maximum pool size
    """
    global _pg_pool

    db_url = database_url or get_database_url()

    if not is_postgres(db_url):
        return  # Skip for SQLite

    if _pg_pool is not None:
        return  # Already initialized

    _pg_pool = SimpleConnectionPool(
        minconn=min_connections,
        maxconn=max_connections,
        dsn=db_url
    )


async def init_async_pool(
    database_url: Optional[str] = None,
    min_size: int = 1,
    max_size: int = 10
) -> None:
    """
    Initialize async PostgreSQL connection pool.

    Args:
        database_url: Database URL
        min_size: Minimum pool size
        max_size: Maximum pool size
    """
    global _async_pool

    db_url = database_url or get_database_url()

    if not is_postgres(db_url):
        return  # Skip for SQLite

    if _async_pool is not None:
        return  # Already initialized

    _async_pool = await asyncpg.create_pool(
        db_url,
        min_size=min_size,
        max_size=max_size
    )


def close_connection_pool() -> None:
    """Close PostgreSQL connection pool."""
    global _pg_pool
    if _pg_pool is not None:
        _pg_pool.closeall()
        _pg_pool = None


async def close_async_pool() -> None:
    """Close async PostgreSQL connection pool."""
    global _async_pool
    if _async_pool is not None:
        await _async_pool.close()
        _async_pool = None


@contextmanager
def get_connection(database_url: Optional[str] = None):
    """
    Get database connection from pool.

    Usage:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
    """
    db_url = database_url or get_database_url()

    if is_postgres(db_url):
        if _pg_pool is None:
            init_connection_pool(db_url)

        conn = _pg_pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            _pg_pool.putconn(conn)
    else:
        # SQLite fallback
        import sqlite3
        db_path = db_url.replace("sqlite:///", "")
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


def get_cursor(conn, dict_cursor: bool = True):
    """
    Get cursor from connection.

    Args:
        conn: Database connection
        dict_cursor: Return rows as dictionaries (only applies to PostgreSQL)

    Returns:
        Cursor object
    """
    import sqlite3
    if isinstance(conn, sqlite3.Connection):
        return conn.cursor()
    # PostgreSQL
    if dict_cursor:
        return conn.cursor(cursor_factory=RealDictCursor)
    return conn.cursor()


def adapt_query(query: str, use_sqlite: bool = False) -> str:
    """
    Adapt PostgreSQL query to SQLite if needed.

    Args:
        query: SQL query with PostgreSQL placeholders (%s)
        use_sqlite: Whether to adapt for SQLite

    Returns:
        Adapted query
    """
    if use_sqlite:
        # Replace %s with ? for SQLite
        query = query.replace("%s", "?")
        # Remove RETURNING clauses (not supported in older SQLite)
        if "RETURNING *" in query:
            query = query.replace(" RETURNING *", "")
        elif "RETURNING" in query and query.count("RETURNING") == 1:
            # Simple RETURNING clause
            query = query.split("RETURNING")[0].strip()
    return query


def dict_from_row(row, use_sqlite: bool = False) -> Optional[Dict[str, Any]]:
    """
    Convert database row to dictionary.

    Args:
        row: Database row
        use_sqlite: Whether row is from SQLite

    Returns:
        Dictionary representation of row
    """
    if row is None:
        return None

    if use_sqlite:
        # SQLite Row object
        return dict(row)
    else:
        # PostgreSQL RealDictRow
        return dict(row)


class DatabaseManager:
    """
    Database manager with migration support.

    Usage:
        db_manager = DatabaseManager()
        await db_manager.create_tables()
    """

    def __init__(self, database_url: Optional[str] = None):
        """Initialize database manager."""
        self.database_url = database_url or get_database_url()
        self.is_postgres = is_postgres(self.database_url)

    def create_table(
        self,
        table_name: str,
        columns: Dict[str, str],
        if_not_exists: bool = True
    ) -> str:
        """
        Generate CREATE TABLE statement.

        Args:
            table_name: Name of table
            columns: Dict of column_name -> column_definition
            if_not_exists: Add IF NOT EXISTS clause

        Returns:
            CREATE TABLE SQL statement

        Example:
            create_table("users", {
                "id": "UUID PRIMARY KEY",
                "email": "VARCHAR(255) UNIQUE NOT NULL",
                "created_at": "TIMESTAMP DEFAULT NOW()"
            })
        """
        exists_clause = "IF NOT EXISTS " if if_not_exists else ""
        column_defs = ",\n  ".join([f"{name} {definition}" for name, definition in columns.items()])

        return f"""
CREATE TABLE {exists_clause}{table_name} (
  {column_defs}
);
"""

    def execute_migration(self, sql: str) -> None:
        """
        Execute migration SQL.

        Args:
            sql: SQL statements to execute
        """
        with get_connection(self.database_url) as conn:
            cursor = get_cursor(conn, dict_cursor=False)
            cursor.execute(sql)


# Convenience functions for services
def init_db(database_url: Optional[str] = None) -> None:
    """Initialize database connection (for startup)."""
    init_connection_pool(database_url)


async def init_async_db(database_url: Optional[str] = None) -> None:
    """Initialize async database connection (for startup)."""
    await init_async_pool(database_url)


def close_db() -> None:
    """Close database connection (for shutdown)."""
    close_connection_pool()


async def close_async_db() -> None:
    """Close async database connection (for shutdown)."""
    await close_async_pool()
