"""
Database migration script for vehicle-manager service.

Creates all necessary tables using common models.
"""

import sys
from pathlib import Path

# Add parent directory to path for common imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.database import DatabaseManager, get_database_url


def create_tables():
    """Create all tables for vehicle-manager service."""

    db_manager = DatabaseManager()

    print(f"Creating tables for database: {get_database_url()}")

    # Assets table (vehicles use common Asset model)
    assets_sql = """
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
    );

    CREATE INDEX IF NOT EXISTS idx_assets_user_id ON assets(user_id);
    CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type);
    CREATE INDEX IF NOT EXISTS idx_assets_vin ON assets(vin);
    """

    # Maintenance records table (using common MaintenanceRecord model)
    maintenance_sql = """
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
    );

    CREATE INDEX IF NOT EXISTS idx_maintenance_asset_id ON maintenance_records(asset_id);
    CREATE INDEX IF NOT EXISTS idx_maintenance_user_id ON maintenance_records(user_id);
    CREATE INDEX IF NOT EXISTS idx_maintenance_date ON maintenance_records(date);
    """

    # Fuel records table (vehicle-specific)
    fuel_records_sql = """
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
    );

    CREATE INDEX IF NOT EXISTS idx_fuel_asset_id ON fuel_records(asset_id);
    CREATE INDEX IF NOT EXISTS idx_fuel_user_id ON fuel_records(user_id);
    CREATE INDEX IF NOT EXISTS idx_fuel_date ON fuel_records(date);
    """

    # Execute all migrations
    tables = [
        ("assets", assets_sql),
        ("maintenance_records", maintenance_sql),
        ("fuel_records", fuel_records_sql),
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
