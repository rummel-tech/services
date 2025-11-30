# Docker Compose Quick Start Guide

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB RAM available
- 20GB disk space

## Quick Start (Development)

### 1. Clone & Navigate

```bash
cd /home/shawn/APP_DEV/workout-planner/applications/backend/python_fastapi_server
```

### 2. Set Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit with your values
nano .env
```

**Minimum required changes**:
```bash
JWT_SECRET=your-unique-secret-min-32-characters-abc123xyz
DB_PASSWORD=secure-database-password
REDIS_PASSWORD=secure-redis-password
```

### 3. Start Services

```bash
# Build and start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api
```

### 4. Verify Deployment

```bash
# Health check
curl http://localhost:8000/health
# Expected: {"status":"ok"}

# Readiness check
curl http://localhost:8000/ready
# Expected: {"status":"ready","db":"ok","redis":"ok"}

# Test through nginx
curl http://localhost/health
```

### 5. Test Authentication

```bash
# Register user
curl -X POST http://localhost/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPass123!",
    "full_name": "Test User"
  }'

# Response includes access_token and refresh_token
```

## Production Deployment

### 1. Generate Secure Secrets

```bash
# Generate JWT secret (32+ characters)
openssl rand -hex 32

# Generate database password
openssl rand -base64 24

# Generate Redis password
openssl rand -base64 24
```

### 2. Update Environment File

```bash
# Edit .env with production values
nano .env
```

**Production .env**:
```bash
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=info

DB_PASSWORD=<generated-db-password>
REDIS_PASSWORD=<generated-redis-password>
JWT_SECRET=<generated-jwt-secret>

CORS_ORIGINS=https://yourdomain.com,https://api.yourdomain.com
```

### 3. Configure SSL (Optional but Recommended)

```bash
# Create SSL directory
mkdir -p ssl

# Copy SSL certificates
cp /path/to/fullchain.pem ssl/
cp /path/to/privkey.pem ssl/

# Uncomment HTTPS server block in nginx.conf
nano nginx.conf
```

### 4. Start Production Services

```bash
# Build with production settings
docker-compose build --no-cache

# Start services
docker-compose up -d

# Verify all healthy
docker-compose ps
```

### 5. Configure Backups

```bash
# Create backup script
cat > backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup database
docker-compose exec -T db pg_dump -U postgres workout_planner | \
  gzip > "$BACKUP_DIR/db_backup_$DATE.sql.gz"

# Backup Redis (if needed)
docker-compose exec -T redis redis-cli --rdb /data/dump.rdb
cp "$(docker volume inspect workout-planner_redis_data -f '{{.Mountpoint}}')/dump.rdb" \
  "$BACKUP_DIR/redis_backup_$DATE.rdb"

# Keep last 30 days
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.rdb" -mtime +30 -delete
EOF

chmod +x backup.sh

# Add to crontab (daily at 2 AM)
echo "0 2 * * * /path/to/backup.sh" | crontab -
```

## Common Commands

### Service Management

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart specific service
docker-compose restart api

# View logs
docker-compose logs -f api
docker-compose logs -f db
docker-compose logs -f redis

# Execute command in container
docker-compose exec api bash
docker-compose exec db psql -U postgres workout_planner
docker-compose exec redis redis-cli -a <REDIS_PASSWORD>
```

### Scaling

```bash
# Scale API to 3 instances
docker-compose up -d --scale api=3

# Nginx will automatically load balance
```

### Updates & Deployment

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose build api
docker-compose up -d api

# Zero-downtime update (scale up, then down)
docker-compose up -d --scale api=4  # Add instances
sleep 30                             # Wait for health checks
docker-compose up -d --scale api=2  # Remove old instances
```

### Monitoring

```bash
# Resource usage
docker stats

# Container health
docker-compose ps

# Application metrics (internal only)
docker-compose exec api curl http://localhost:8000/metrics

# Cache statistics
curl http://localhost:8000/cache/stats
```

## Database Management

### Access Database

```bash
# Connect to database
docker-compose exec db psql -U postgres workout_planner

# List tables
\dt

# Check user count
SELECT COUNT(*) FROM users;
```

### Manual Backup

```bash
# Backup to file
docker-compose exec db pg_dump -U postgres workout_planner > backup.sql

# Restore from file
cat backup.sql | docker-compose exec -T db psql -U postgres workout_planner
```

### Database Migrations

```bash
# Schema is auto-initialized on first run
# To reset database (WARNING: deletes all data)
docker-compose down -v  # Remove volumes
docker-compose up -d    # Recreate with fresh DB
```

## Redis Management

### Access Redis

```bash
# Connect to Redis
docker-compose exec redis redis-cli -a <REDIS_PASSWORD>

# Check keys
KEYS *

# Monitor commands
MONITOR

# Get cache statistics
INFO stats
```

### Clear Cache

```bash
# Clear all cache (will rebuild automatically)
docker-compose exec redis redis-cli -a <REDIS_PASSWORD> FLUSHDB

# Clear specific pattern
docker-compose exec redis redis-cli -a <REDIS_PASSWORD> \
  --eval "return redis.call('del', unpack(redis.call('keys', ARGV[1])))" \
  , "readiness:*"
```

## Troubleshooting

### API Won't Start

```bash
# Check logs
docker-compose logs api

# Common issues:
# 1. Database not ready - wait for db health check
# 2. Redis connection failed - check REDIS_PASSWORD
# 3. Port conflict - change port in docker-compose.yml
```

### Database Connection Errors

```bash
# Verify database is running
docker-compose ps db

# Check database logs
docker-compose logs db

# Test connection manually
docker-compose exec api python3 -c "
import psycopg2
conn = psycopg2.connect('postgresql://postgres:changeme@db:5432/workout_planner')
print('Connected!')
"
```

### High Memory Usage

```bash
# Check resource usage
docker stats

# Reduce API workers in Dockerfile:
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

# Reduce Redis memory limit in docker-compose.yml:
--maxmemory 128mb
```

### Performance Issues

```bash
# Check cache hit rate
curl http://localhost:8000/cache/stats

# Monitor Redis
docker-compose exec redis redis-cli -a <REDIS_PASSWORD> INFO stats

# Check slow queries (if any)
docker-compose exec db psql -U postgres -c "
  SELECT query, calls, mean_exec_time
  FROM pg_stat_statements
  ORDER BY mean_exec_time DESC
  LIMIT 10;
"
```

## Production Checklist

Before going live:

- [ ] Secrets set in .env (JWT_SECRET, passwords)
- [ ] ENVIRONMENT=production
- [ ] DEBUG=false
- [ ] SSL certificates configured
- [ ] CORS origins restricted
- [ ] Backups configured (daily)
- [ ] Monitoring configured
- [ ] Health checks passing
- [ ] Load tested (Locust)
- [ ] Logs reviewed
- [ ] Rollback plan documented

## Resource Requirements

### Minimum (Development)
- CPU: 2 cores
- RAM: 2GB
- Disk: 10GB

### Recommended (Production)
- CPU: 4 cores
- RAM: 4GB
- Disk: 50GB (with backups)

### Expected Usage
- API: 512MB RAM, 0.5 CPU
- Database: 256MB RAM, 0.25 CPU
- Redis: 256MB RAM, 0.1 CPU
- Nginx: 128MB RAM, 0.15 CPU

## Cost Estimate

**VPS Hosting** (DigitalOcean, Linode, etc.):
- 4 vCPU, 8GB RAM: ~$40/month
- 2 vCPU, 4GB RAM: ~$20/month

**Includes**:
- All services (API, DB, Redis, Nginx)
- 50GB storage
- 4TB transfer

## Support

For issues or questions:
- Check logs: `docker-compose logs -f`
- Review documentation: See [docs/DEPLOYMENT.md](../../../docs/DEPLOYMENT.md)
- Check health: `curl http://localhost:8000/ready`

## Next Steps

1. **Configure monitoring**: Set up Grafana + Prometheus
2. **Add SSL**: Get Let's Encrypt certificate
3. **Configure backups**: Automate daily backups
4. **Load test**: Run Locust tests
5. **Set up CI/CD**: Automate deployments

---

**Status**: Production-ready with Docker Compose
**Version**: 1.0.0
**Date**: 2025-11-21
