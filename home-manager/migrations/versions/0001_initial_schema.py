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
        CREATE TABLE IF NOT EXISTS tasks (
            id UUID PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            title VARCHAR(500) NOT NULL,
            description TEXT,
            status VARCHAR(50) DEFAULT 'pending',
            priority VARCHAR(50) DEFAULT 'medium',
            category VARCHAR(100) NOT NULL,
            due_date TIMESTAMP,
            completed_at TIMESTAMP,
            estimated_minutes INTEGER,
            tags TEXT[],
            context JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id UUID PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            title VARCHAR(500) NOT NULL,
            description TEXT,
            category VARCHAR(100) NOT NULL,
            target_value FLOAT,
            target_unit VARCHAR(50),
            target_date TIMESTAMP,
            current_value FLOAT,
            is_active BOOLEAN DEFAULT TRUE,
            progress_percentage INTEGER DEFAULT 0,
            notes TEXT,
            context JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_goals_user_id ON goals(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_goals_is_active ON goals(is_active)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id UUID PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            asset_type VARCHAR(50) NOT NULL,
            category VARCHAR(100) NOT NULL,
            manufacturer VARCHAR(255),
            model_number VARCHAR(255),
            serial_number VARCHAR(255),
            vin VARCHAR(50),
            purchase_date TIMESTAMP,
            purchase_price FLOAT,
            current_value FLOAT,
            condition VARCHAR(50) DEFAULT 'good',
            location VARCHAR(255),
            notes TEXT,
            context JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_assets_user_id ON assets(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(asset_type)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id UUID PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            title VARCHAR(500) NOT NULL,
            description TEXT,
            status VARCHAR(50) DEFAULT 'planned',
            category VARCHAR(100) NOT NULL,
            priority VARCHAR(50) DEFAULT 'medium',
            start_date TIMESTAMP,
            target_date TIMESTAMP,
            completed_date TIMESTAMP,
            budget FLOAT,
            actual_cost FLOAT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS project_items (
            id UUID PRIMARY KEY,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            item_id UUID NOT NULL,
            item_type VARCHAR(50) NOT NULL,
            quantity_needed FLOAT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_items_project_id ON project_items(project_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id UUID PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            quantity FLOAT DEFAULT 1.0,
            unit VARCHAR(50) DEFAULT 'each',
            unit_cost FLOAT,
            total_cost FLOAT,
            supplier VARCHAR(255),
            purchased BOOLEAN DEFAULT FALSE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_materials_user_id ON materials(user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            id UUID PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            type VARCHAR(50) NOT NULL,
            url TEXT,
            description TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_resources_user_id ON resources(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_resources_type ON resources(type)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS resources")
    op.execute("DROP TABLE IF EXISTS materials")
    op.execute("DROP TABLE IF EXISTS project_items")
    op.execute("DROP TABLE IF EXISTS projects")
    op.execute("DROP TABLE IF EXISTS assets")
    op.execute("DROP TABLE IF EXISTS goals")
    op.execute("DROP TABLE IF EXISTS tasks")
