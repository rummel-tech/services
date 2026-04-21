# Database Migrations

Managed with [Alembic](https://alembic.sqlalchemy.org/).

## Common commands

```bash
# Apply all pending migrations
alembic upgrade head

# Roll back one step
alembic downgrade -1

# Show current revision
alembic current

# Show migration history
alembic history

# Generate a new migration (edit it before committing)
alembic revision -m "describe_your_change"
```

## Environment

Set `DATABASE_URL` before running. Defaults to the service's dev SQLite file.

```bash
export DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
alembic upgrade head
```
