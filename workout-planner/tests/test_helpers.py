"""Shared test utilities for workout-planner tests."""
import sqlite3
import threading
import os
import sys
import importlib

# Thread-safe code counter
_code_lock = threading.Lock()
_code_counter = 0


def setup_test_database(db_path: str, reset_codes: bool = True) -> None:
    """Set up a test database with proper module reloading.

    This function:
    1. Sets DATABASE_URL environment variable
    2. Clears settings cache
    3. Removes cached modules (database, main, routers) to force fresh imports
    4. Initializes the database schema
    5. Creates test registration codes
    6. Optionally resets the code counter

    Args:
        db_path: Path to the SQLite test database file
        reset_codes: If True, reset the code counter to 0 (default True)
    """
    # Set environment variable
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    # Enforce authentication for tests that expect real auth checks
    os.environ["DISABLE_AUTH"] = "false"

    # Clear settings cache
    from settings import get_settings
    get_settings.cache_clear()

    # Remove ALL app modules to ensure fresh import with new database URL
    # This includes main, all routers, database, and related modules
    modules_to_remove = [m for m in list(sys.modules.keys()) if any(
        m == name or m.startswith(f'{name}.')
        for name in ['main', 'database', 'routers', 'auth_service', 'ai_chat_service', 'ai_engine']
    )]
    for m in modules_to_remove:
        del sys.modules[m]

    # Fresh import of database module (will read new DATABASE_URL)
    import database
    database.init_sqlite()

    # Create test registration codes
    create_test_registration_codes(db_path)

    # Reset code counter so each test module starts fresh
    if reset_codes:
        reset_code_counter()


def clear_settings_cache() -> None:
    """Clear the cached settings to allow new DATABASE_URL to be picked up."""
    from settings import get_settings
    get_settings.cache_clear()


def create_test_registration_codes(db_path: str, count: int = 500) -> None:
    """Create multiple registration codes in the test database.

    Args:
        db_path: Path to the SQLite test database
        count: Number of codes to create
    """
    conn = sqlite3.connect(db_path)
    for i in range(count):
        conn.execute(
            "INSERT OR IGNORE INTO registration_codes (code, is_used) VALUES (?, 0)",
            (f"TESTCODE{i:04d}",)
        )
    conn.commit()
    conn.close()


def get_next_registration_code() -> str:
    """Get the next unique test registration code (thread-safe)."""
    global _code_counter
    with _code_lock:
        code = f"TESTCODE{_code_counter:04d}"
        _code_counter += 1
        return code


def reset_code_counter() -> None:
    """Reset the code counter (useful for test isolation)."""
    global _code_counter
    with _code_lock:
        _code_counter = 0
