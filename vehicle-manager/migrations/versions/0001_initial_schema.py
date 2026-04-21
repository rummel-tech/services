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
        CREATE TABLE IF NOT EXISTS assets (
            id UUID PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            asset_type VARCHAR(50) NOT NULL DEFAULT 'vehicle',
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_assets_vin ON assets(vin)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_records (
            id UUID PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            maintenance_type VARCHAR(100) NOT NULL,
            date TIMESTAMP NOT NULL,
            cost FLOAT,
            description TEXT,
            performed_by VARCHAR(255),
            next_due_date TIMESTAMP,
            next_due_mileage INTEGER,
            notes TEXT,
            context JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_maintenance_asset_id ON maintenance_records(asset_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_maintenance_user_id ON maintenance_records(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_maintenance_date ON maintenance_records(date)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS fuel_records (
            id UUID PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            date TIMESTAMP NOT NULL,
            mileage INTEGER NOT NULL,
            gallons FLOAT NOT NULL,
            cost FLOAT NOT NULL,
            price_per_gallon FLOAT,
            fuel_type VARCHAR(50) DEFAULT 'regular',
            mpg FLOAT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_fuel_asset_id ON fuel_records(asset_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fuel_user_id ON fuel_records(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fuel_date ON fuel_records(date)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fuel_records")
    op.execute("DROP TABLE IF EXISTS maintenance_records")
    op.execute("DROP TABLE IF EXISTS assets")
