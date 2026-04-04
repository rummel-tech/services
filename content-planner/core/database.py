import json
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.database import (
    get_database_url,
    is_sqlite,
    get_connection,
    get_cursor,
    adapt_query,
    dict_from_row,
    init_connection_pool,
    close_connection_pool,
)

logger = logging.getLogger(__name__)

DATABASE_URL = get_database_url() or "sqlite:///content_dev.db"
USE_SQLITE = is_sqlite(DATABASE_URL)

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS pillars (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    color INTEGER NOT NULL DEFAULT 4280391411,
    priority_weight REAL NOT NULL DEFAULT 1.0,
    is_quarterly_focus INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

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

CREATE TABLE IF NOT EXISTS content_items (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    source_id TEXT,
    title TEXT NOT NULL,
    url TEXT,
    type TEXT NOT NULL DEFAULT 'episode',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    published_at TEXT,
    topics TEXT NOT NULL DEFAULT '[]',
    pillar_id TEXT,
    mode TEXT NOT NULL DEFAULT 'tactical',
    status TEXT NOT NULL DEFAULT 'inbox',
    play_position_ms INTEGER NOT NULL DEFAULT 0,
    play_completed_at TEXT,
    skip_count INTEGER NOT NULL DEFAULT 0,
    redundant_flag INTEGER NOT NULL DEFAULT 0,
    last_skipped_at TEXT,
    similarity_key TEXT,
    queue_position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id),
    FOREIGN KEY (pillar_id) REFERENCES pillars(id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    context TEXT NOT NULL DEFAULT 'idle',
    mode TEXT NOT NULL DEFAULT 'tactical',
    content_item_id TEXT,
    outcome TEXT,
    listened_duration_ms INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (content_item_id) REFERENCES content_items(id)
);

CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    content_item_id TEXT NOT NULL,
    pillar_id TEXT,
    title TEXT NOT NULL,
    insights TEXT NOT NULL DEFAULT '[]',
    applications TEXT NOT NULL DEFAULT '[]',
    behavior_change TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY (content_item_id) REFERENCES content_items(id),
    FOREIGN KEY (pillar_id) REFERENCES pillars(id)
);

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
    quarterly_focus_pillar_id TEXT,
    updated_at TEXT NOT NULL
);
"""


def init_db():
    """Initialize database tables."""
    if USE_SQLITE:
        _init_sqlite()
    else:
        _init_pg()


def _init_sqlite():
    import sqlite3
    db_path = DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    try:
        for statement in CREATE_TABLES.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
        logger.info("SQLite tables initialized")
    finally:
        conn.close()


def _init_pg():
    import psycopg2
    with get_connection() as conn:
        with conn.cursor() as cur:
            for statement in CREATE_TABLES.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    cur.execute(stmt)
        conn.commit()
    logger.info("PostgreSQL tables initialized")


async def init_pg_pool():
    init_connection_pool(DATABASE_URL)


async def close_pg_pool():
    close_connection_pool()
