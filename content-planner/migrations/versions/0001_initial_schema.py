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
        CREATE TABLE IF NOT EXISTS pillars (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            color INTEGER NOT NULL DEFAULT 4280391411,
            priority_weight REAL NOT NULL DEFAULT 1.0,
            is_quarterly_focus INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_pillars_user_id ON pillars(user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            type TEXT NOT NULL DEFAULT 'podcast',
            trust_level TEXT NOT NULL DEFAULT 'neutral',
            blocked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sources_user_id ON sources(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sources_trust ON sources(trust_level)")

    op.execute("""
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
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_content_user_id ON content_items(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_content_status ON content_items(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_content_pillar ON content_items(pillar_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_content_queue ON content_items(queue_position)")

    op.execute("""
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
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at)")

    op.execute("""
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
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_summaries_user_id ON summaries(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_summaries_content ON summaries(content_item_id)")

    op.execute("""
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
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_settings")
    op.execute("DROP TABLE IF EXISTS summaries")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS content_items")
    op.execute("DROP TABLE IF EXISTS sources")
    op.execute("DROP TABLE IF EXISTS pillars")
