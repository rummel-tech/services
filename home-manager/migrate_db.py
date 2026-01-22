"""
Database migration script for home-manager service.

Creates all necessary tables using common models.
"""

import sys
from pathlib import Path

# Add parent directory to path for common imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.database import DatabaseManager, get_database_url


def create_tables():
    """Create all tables for home-manager service."""

    db_manager = DatabaseManager()

    print(f"Creating tables for database: {get_database_url()}")

    # Tasks table (using common Task model)
    tasks_sql = """
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
    );

    CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
    CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
    """

    # Goals table (using common Goal model)
    goals_sql = """
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
    );

    CREATE INDEX IF NOT EXISTS idx_goals_user_id ON goals(user_id);
    CREATE INDEX IF NOT EXISTS idx_goals_is_active ON goals(is_active);
    """

    # Assets table (using common Asset model)
    assets_sql = """
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
    );

    CREATE INDEX IF NOT EXISTS idx_assets_user_id ON assets(user_id);
    CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type);
    CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);
    """

    # Projects table (home-manager specific)
    projects_sql = """
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
    );

    CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
    CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
    """

    # Project items (tools, materials, resources for projects)
    project_items_sql = """
    CREATE TABLE IF NOT EXISTS project_items (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        item_id UUID NOT NULL,
        item_type VARCHAR(50) NOT NULL,
        quantity_needed FLOAT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_project_items_project_id ON project_items(project_id);
    """

    # Materials table (home-manager specific)
    materials_sql = """
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
    );

    CREATE INDEX IF NOT EXISTS idx_materials_user_id ON materials(user_id);
    """

    # Resources table (documents, guides, etc.)
    resources_sql = """
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
    );

    CREATE INDEX IF NOT EXISTS idx_resources_user_id ON resources(user_id);
    CREATE INDEX IF NOT EXISTS idx_resources_type ON resources(type);
    """

    # Execute all migrations
    tables = [
        ("tasks", tasks_sql),
        ("goals", goals_sql),
        ("assets", assets_sql),
        ("projects", projects_sql),
        ("project_items", project_items_sql),
        ("materials", materials_sql),
        ("resources", resources_sql),
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
