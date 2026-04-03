"""
Database migration script for content-planner service.

Creates all necessary tables for audio-first content consumption tracking.
"""

import sys
from pathlib import Path

# Add parent directory to path for common imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.database import DatabaseManager, get_database_url


def create_tables():
    """Create all tables for content-planner service."""

    db_manager = DatabaseManager()

    print(f"Creating tables for database: {get_database_url()}")

    pillars_sql = """
    CREATE TABLE IF NOT EXISTS pillars (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        color INTEGER NOT NULL DEFAULT 4280391411,
        priority_weight REAL NOT NULL DEFAULT 1.0,
        is_quarterly_focus INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_pillars_user_id ON pillars(user_id);
    """

    sources_sql = """
    CREATE TABLE IF NOT EXISTS sources (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT,
        type TEXT NOT NULL DEFAULT 'podcast',
        trust_level TEXT NOT NULL DEFAULT 'neutral',
        blocked INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_sources_user_id ON sources(user_id);
    CREATE INDEX IF NOT EXISTS idx_sources_trust ON sources(trust_level);
    """

    content_items_sql = """
    CREATE TABLE IF NOT EXISTS content_items (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
        title TEXT NOT NULL,
        url TEXT,
        type TEXT NOT NULL DEFAULT 'episode',
        duration_ms INTEGER NOT NULL DEFAULT 0,
        published_at TEXT,
        topics TEXT NOT NULL DEFAULT '[]',
        pillar_id TEXT REFERENCES pillars(id) ON DELETE SET NULL,
        mode TEXT NOT NULL DEFAULT 'tactical',
        status TEXT NOT NULL DEFAULT 'inbox',
        play_position_ms INTEGER NOT NULL DEFAULT 0,
        play_completed_at TEXT,
        skip_count INTEGER NOT NULL DEFAULT 0,
        redundant_flag INTEGER NOT NULL DEFAULT 0,
        last_skipped_at TEXT,
        similarity_key TEXT,
        queue_position INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_content_user_id ON content_items(user_id);
    CREATE INDEX IF NOT EXISTS idx_content_status ON content_items(status);
    CREATE INDEX IF NOT EXISTS idx_content_pillar ON content_items(pillar_id);
    CREATE INDEX IF NOT EXISTS idx_content_queue ON content_items(queue_position);
    """

    sessions_sql = """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        context TEXT NOT NULL DEFAULT 'idle',
        mode TEXT NOT NULL DEFAULT 'tactical',
        content_item_id TEXT REFERENCES content_items(id) ON DELETE SET NULL,
        outcome TEXT,
        listened_duration_ms INTEGER NOT NULL DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
    """

    summaries_sql = """
    CREATE TABLE IF NOT EXISTS summaries (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        content_item_id TEXT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
        pillar_id TEXT REFERENCES pillars(id) ON DELETE SET NULL,
        title TEXT NOT NULL,
        insights TEXT NOT NULL DEFAULT '[]',
        applications TEXT NOT NULL DEFAULT '[]',
        behavior_change TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_summaries_user_id ON summaries(user_id);
    CREATE INDEX IF NOT EXISTS idx_summaries_content ON summaries(content_item_id);
    """

    user_settings_sql = """
    CREATE TABLE IF NOT EXISTS user_settings (
        user_id TEXT PRIMARY KEY,
        pillar_ids TEXT NOT NULL DEFAULT '[]',
        trusted_source_ids TEXT NOT NULL DEFAULT '[]',
        blocked_source_ids TEXT NOT NULL DEFAULT '[]',
        context_mode_map TEXT NOT NULL DEFAULT '{}',
        queue_total_cap INTEGER NOT NULL DEFAULT 10,
        queue_per_pillar_cap INTEGER NOT NULL DEFAULT 5,
        queue_per_mode_cap INTEGER NOT NULL DEFAULT 5,
        start_behavior TEXT NOT NULL DEFAULT 'auto',
        notif_weekly_review INTEGER NOT NULL DEFAULT 1,
        notif_queue_empty INTEGER NOT NULL DEFAULT 1,
        notif_inbox_overflow INTEGER NOT NULL DEFAULT 0,
        notif_inbox_overflow_threshold INTEGER NOT NULL DEFAULT 20,
        quarterly_focus_pillar_id TEXT REFERENCES pillars(id) ON DELETE SET NULL,
        updated_at TEXT NOT NULL
    );
    """

    tables = [
        ("pillars", pillars_sql),
        ("sources", sources_sql),
        ("content_items", content_items_sql),
        ("sessions", sessions_sql),
        ("summaries", summaries_sql),
        ("user_settings", user_settings_sql),
    ]

    for table_name, sql in tables:
        try:
            print(f"Creating table: {table_name}")
            db_manager.execute_migration(sql)
            print(f"✓ {table_name} created successfully")
        except Exception as e:
            print(f"✗ Error creating {table_name}: {e}")

    print("\nDatabase migration completed!")


if __name__ == "__main__":
    create_tables()
