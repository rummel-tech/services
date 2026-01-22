# Workout Planner - Quick Start Guide

## Server Running Locally

**Status**: ✅ RUNNING
**URL**: http://localhost:8000
**Environment**: Development
**Database**: SQLite (fitness_dev.db)

## Health Check Endpoints

Test that the server is running and healthy:

```bash
# Basic health check
curl http://localhost:8000/health

# Liveness check (Kubernetes-style)
curl http://localhost:8000/healthz

# Readiness check with dependencies
curl http://localhost:8000/readyz

# Detailed database health
curl http://localhost:8000/health/db
```

## API Documentation

View the complete API documentation in your browser:

```bash
# Swagger UI (interactive)
xdg-open http://localhost:8000/docs

# ReDoc (clean documentation)
xdg-open http://localhost:8000/redoc
```

## Database Migrations

Manage database schema changes with Alembic:

```bash
# Check current migration version
alembic current

# View migration history
alembic history --verbose

# Apply pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Create a new migration
alembic revision -m "description"
```

## Testing Endpoints

### Register a User

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123",
    "full_name": "Test User"
  }'
```

### Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123"
  }'
```

### Join Waitlist

```bash
curl -X POST http://localhost:8000/waitlist \
  -H "Content-Type: application/json" \
  -d '{"email": "waitlist@example.com"}'
```

### Get Readiness Score

```bash
# First, get your access token from login
TOKEN="your_access_token_here"

curl http://localhost:8000/readiness?user_id=your_user_id \
  -H "Authorization: Bearer $TOKEN"
```

## Monitoring

### View Prometheus Metrics

```bash
# Get all metrics
curl http://localhost:8000/metrics

# Filter specific metrics
curl http://localhost:8000/metrics | grep workout_planner
```

### View Server Logs

```bash
# Follow logs in real-time
tail -f /tmp/workout-planner.log

# View last 50 lines
tail -50 /tmp/workout-planner.log
```

## Server Management

### Stop Server

```bash
# Find the process ID
ps aux | grep uvicorn

# Kill the server
kill <PID>

# Or force kill
kill -9 <PID>
```

### Restart Server

```bash
# Stop current server (if running)
pkill -f "uvicorn main:app"

# Start fresh
cd /home/shawn/_Projects/services/workout-planner
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

## Development Workflow

### Make Code Changes

The server runs with `--reload`, so code changes are automatically detected:

1. Edit files in your editor
2. Save changes
3. Server automatically reloads
4. Test your changes

### Run Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_health.py

# Run with coverage
pytest --cov=. --cov-report=html

# View coverage report
xdg-open htmlcov/index.html
```

### Create a Migration

When you modify database schema:

```bash
# 1. Create migration file
alembic revision -m "add_new_column_to_users"

# 2. Edit the migration file
#    migrations/versions/<revision>_add_new_column_to_users.py

# 3. Add your upgrade logic
def upgrade() -> None:
    op.execute("""
        ALTER TABLE users
        ADD COLUMN new_column TEXT
    """)

# 4. Add your downgrade logic
def downgrade() -> None:
    op.execute("""
        ALTER TABLE users
        DROP COLUMN new_column
    """)

# 5. Test the migration
alembic upgrade head

# 6. Test the rollback
alembic downgrade -1

# 7. Re-apply
alembic upgrade head
```

## Production Deployment

When ready to deploy to production:

### 1. Pre-Deployment Checklist

```bash
# Run all tests
pytest

# Check migration status
alembic current

# Verify health endpoints
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
```

### 2. Backup Database

```bash
# AWS RDS
aws rds create-db-snapshot \
  --db-instance-identifier workout-planner-prod \
  --db-snapshot-identifier pre-migration-$(date +%Y%m%d)
```

### 3. Apply Migrations

```bash
# SSH to production server
ssh production-server

# Navigate to app directory
cd /app/workout-planner

# Activate virtual environment
source .venv/bin/activate

# Apply migrations
alembic upgrade head

# Verify
alembic current
```

### 4. Deploy Application

```bash
# Push to main branch (triggers CI/CD)
git push origin main

# Or manual deployment
docker build -t workout-planner:latest .
docker push workout-planner:latest
```

### 5. Verify Deployment

```bash
# Check health endpoints
curl https://api.workout-planner.com/healthz
curl https://api.workout-planner.com/readyz
curl https://api.workout-planner.com/health/db

# Monitor logs
kubectl logs -f deployment/workout-planner

# Or ECS logs
aws logs tail /ecs/workout-planner --follow
```

## Troubleshooting

### Server Won't Start

```bash
# Check if port is already in use
lsof -i :8000

# Check for Python errors
python main.py

# Check environment variables
env | grep DATABASE
```

### Database Issues

```bash
# Check database file exists
ls -lh fitness_dev.db

# Check database is not locked
lsof fitness_dev.db

# Verify tables exist
sqlite3 fitness_dev.db ".tables"
```

### Migration Issues

```bash
# Check migration status
alembic current

# View migration history
alembic history

# Force to specific version (careful!)
alembic stamp head
```

### API Returns 500 Errors

```bash
# Check server logs
tail -50 /tmp/workout-planner.log

# Check database health
curl http://localhost:8000/health/db

# Verify dependencies
pip list | grep -E "fastapi|uvicorn|alembic"
```

## Next Steps

1. **Explore API**: Open http://localhost:8000/docs
2. **Run Tests**: `pytest tests/`
3. **Create User**: Use the `/auth/register` endpoint
4. **Test Workflows**: Try the health data → readiness score flow
5. **Review Documentation**: See `/migrations/README.md` for migration details

## Support

- **Migrations**: See `migrations/README.md`
- **Production Readiness**: See `PRODUCTION_READINESS_REPORT.md`
- **Migration Summary**: See `MIGRATION_READINESS_SUMMARY.md`
- **API Docs**: http://localhost:8000/docs

---

**Server is running at**: http://localhost:8000
**Process ID**: Check with `ps aux | grep uvicorn`
**Logs**: `/tmp/workout-planner.log`
