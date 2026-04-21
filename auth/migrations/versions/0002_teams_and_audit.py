"""Add teams, team_members, team_invitations, and audit_logs tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-20
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            event TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_event ON audit_logs(event)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            plan TEXT NOT NULL DEFAULT 'team',
            max_members INTEGER NOT NULL DEFAULT 10,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_teams_owner ON teams(owner_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_teams_slug ON teams(slug)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'member',
            invited_by TEXT REFERENCES users(id),
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(team_id, user_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS team_invitations (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            invited_by TEXT NOT NULL REFERENCES users(id),
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            accepted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_invitations_team ON team_invitations(team_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_invitations_token ON team_invitations(token)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_invitations_email ON team_invitations(email)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS team_invitations")
    op.execute("DROP TABLE IF EXISTS team_members")
    op.execute("DROP TABLE IF EXISTS teams")
    op.execute("DROP TABLE IF EXISTS audit_logs")
