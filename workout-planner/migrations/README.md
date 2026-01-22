# Database Migrations

This directory contains Alembic database migrations for the Workout Planner backend.

## Overview

Alembic is a lightweight database migration tool for use with SQLAlchemy. It provides version control for your database schema, allowing you to safely modify tables, columns, and indexes in production.

## Quick Start

### View Current Status

```bash
# Show current migration version
alembic current

# Show migration history
alembic history --verbose
```

### Apply Migrations

```bash
# Upgrade to latest version
alembic upgrade head

# Upgrade one version at a time
alembic upgrade +1

# Upgrade to specific version
alembic upgrade <revision_id>
```

### Rollback Migrations

```bash
# Downgrade one version
alembic downgrade -1

# Downgrade to specific version
alembic downgrade <revision_id>

# Rollback all migrations (DANGEROUS!)
alembic downgrade base
```

## Creating New Migrations

### Manual Migration (Recommended for this project)

Since we don't use SQLAlchemy ORM models, create migrations manually:

```bash
# Create a new migration file
alembic revision -m "add_column_to_users"
```

This creates a new file in `migrations/versions/`. Edit the `upgrade()` and `downgrade()` functions:

```python
def upgrade() -> None:
    """Add new column."""
    op.execute("""
        ALTER TABLE users
        ADD COLUMN phone_number TEXT
    """)

def downgrade() -> None:
    """Remove column."""
    op.execute("""
        ALTER TABLE users
        DROP COLUMN phone_number
    """)
```

### Migration Best Practices

1. **Always test migrations on development first**
   ```bash
   # In dev environment
   alembic upgrade head
   # Test your app
   # If issues, rollback
   alembic downgrade -1
   ```

2. **Write both upgrade AND downgrade**
   - Every migration must be reversible
   - Test the downgrade function

3. **Use IF EXISTS/IF NOT EXISTS when appropriate**
   - Makes migrations idempotent
   - Safe to re-run if needed

4. **One logical change per migration**
   - Don't mix adding columns with dropping tables
   - Easier to debug and rollback

5. **Add comments to complex migrations**
   - Explain why the change is needed
   - Document any data transformations

6. **Back up production before migrating**
   ```bash
   # AWS RDS automatic backups should be enabled
   # Or manual snapshot
   aws rds create-db-snapshot --db-instance-identifier workout-planner --db-snapshot-identifier pre-migration-$(date +%Y%m%d)
   ```

## Production Deployment

### Step 1: Backup Database

```bash
# Create snapshot (AWS RDS)
aws rds create-db-snapshot \
  --db-instance-identifier workout-planner-prod \
  --db-snapshot-identifier migration-$(date +%Y%m%d-%H%M)
```

### Step 2: Apply Migration

```bash
# SSH into production server or run from CI/CD
cd /app/workout-planner
source .venv/bin/activate

# Show pending migrations
alembic current
alembic history

# Apply migrations
alembic upgrade head

# Verify
alembic current
```

### Step 3: Restart Application

```bash
# ECS will handle this automatically on deploy
# Or restart manually
supervisorctl restart workout-planner
```

### Step 4: Monitor

- Check application logs
- Test critical endpoints
- Monitor error rates

### Rollback Plan

If migration causes issues:

```bash
# Rollback migration
alembic downgrade -1

# Restore from snapshot (if needed)
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier workout-planner-prod-restored \
  --db-snapshot-identifier migration-YYYYMMDD-HHMM

# Update DNS/connection strings to point to restored instance
```

## Configuration

The database URL is automatically loaded from `core/settings.py` via environment variables:

- **Development**: Uses `DATABASE_URL` from `.env` (typically SQLite)
- **Production**: Uses `DATABASE_URL` from environment (PostgreSQL)

## Existing Auto-Initialization

**Important**: The `core/database.py` file still contains auto-initialization code for backward compatibility with development environments:

- `init_sqlite()` - Creates tables if using SQLite
- `init_postgres()` - Creates tables if using PostgreSQL

**For production**: Use Alembic migrations instead of auto-initialization. The auto-init code will be phased out once all environments are using migrations.

## Migration History

### 561152f2b473 - Initial Schema (2026-01-22)

Creates all initial tables:
- users, registration_codes, waitlist
- user_goals, goal_plans
- health_samples, health_metrics
- chat_sessions, chat_messages
- weekly_plans, daily_plans
- workouts, strength_metrics, swim_metrics
- All indexes

This migration captures the existing schema from `database.py` for version control going forward.

## Troubleshooting

### Migration fails with "table already exists"

If tables were created by auto-initialization, mark them as migrated:

```bash
# Mark current state without running migrations
alembic stamp head
```

### Database is out of sync

```bash
# Show current version
alembic current

# Show what would be applied
alembic upgrade head --sql

# Force to specific version (careful!)
alembic stamp <revision_id>
```

### Need to edit a migration after applying

```bash
# Roll back
alembic downgrade -1

# Edit the migration file
vim migrations/versions/<revision>.py

# Re-apply
alembic upgrade +1
```

## References

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Production Readiness Report](../PRODUCTION_READINESS_REPORT.md)
