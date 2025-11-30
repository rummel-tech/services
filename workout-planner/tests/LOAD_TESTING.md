# Load Testing Guide

This guide explains how to perform load testing on the Workout Planner API using Locust.

## Prerequisites

1. **Install Locust** (already done if you followed Phase 2 setup):
   ```bash
   source .venv/bin/activate
   pip install locust
   ```

2. **Start the FastAPI server**:
   ```bash
   source .venv/bin/activate
   uvicorn main:app --reload --port 8000
   ```

## Running Load Tests

### Interactive Mode with Web UI

Run Locust with the web interface for real-time monitoring:

```bash
cd /home/shawn/APP_DEV/workout-planner/applications/backend/python_fastapi_server
source .venv/bin/activate
locust -f tests/locustfile.py --host=http://localhost:8000
```

Then open your browser to http://localhost:8089 and configure:
- **Number of users**: Start with 10, gradually increase to 100+
- **Spawn rate**: 5-10 users per second
- **Run time**: 2-5 minutes

### Headless Mode (CLI only)

Run load tests without the web UI:

```bash
# Light load test: 50 users, 10 second ramp-up, 2 minute duration
locust -f tests/locustfile.py --host=http://localhost:8000 \
  --users 50 --spawn-rate 10 --run-time 2m --headless

# Medium load test: 100 users, 10 second ramp-up, 5 minute duration
locust -f tests/locustfile.py --host=http://localhost:8000 \
  --users 100 --spawn-rate 10 --run-time 5m --headless

# Heavy load test: 500 users, 50 second ramp-up, 10 minute duration
locust -f tests/locustfile.py --host=http://localhost:8000 \
  --users 500 --spawn-rate 50 --run-time 10m --headless
```

### Test Specific User Types

Test only health monitoring users:

```bash
locust -f tests/locustfile.py --host=http://localhost:8000 \
  --users 100 --spawn-rate 10 --run-time 3m --headless \
  HealthMonitoringUser
```

Test only workout plan users:

```bash
locust -f tests/locustfile.py --host=http://localhost:8000 \
  --users 100 --spawn-rate 10 --run-time 3m --headless \
  workout-plannerUser
```

## Understanding the Results

### Key Metrics to Monitor

1. **Response Time**:
   - **Median**: 50th percentile response time (should be < 200ms for API endpoints)
   - **95th Percentile**: 95% of requests complete within this time (should be < 500ms)
   - **99th Percentile**: 99% of requests complete within this time (should be < 1000ms)

2. **Request Rate (RPS)**:
   - Total requests per second the server can handle
   - Higher is better, but must maintain acceptable response times

3. **Failure Rate**:
   - Percentage of requests that fail (should be < 1%)
   - Review failed requests for patterns (e.g., timeouts, 500 errors)

4. **Concurrent Users**:
   - Number of simultaneous users the system can support
   - Goal: 100+ concurrent users with < 500ms P95 response time

### Example Good Results

```
Name                                   # reqs  # fails  Avg   Min   Max  Median  P95   P99   RPS
/auth/register                         1000    0        45    12    234  42      89    150   20.0
/daily-plans/[user_id]/[date]          3000    0        32    8     156  28      65    98    60.0
/health/samples                        2500    5        58    15    892  52      120   245   50.0
/readiness                             1500    0        125   45    456  118     245   356   30.0
```

### Warning Signs

- **P95 > 1000ms**: Server struggling under load
- **Failure rate > 5%**: System instability, investigate errors
- **Increasing response times**: Potential memory leak or resource exhaustion
- **Database connection errors**: Connection pool exhausted
- **502/503 errors**: Server overloaded

## Load Testing Scenarios

### 1. Baseline Performance Test

**Goal**: Establish baseline metrics with light load

```bash
locust -f tests/locustfile.py --host=http://localhost:8000 \
  --users 10 --spawn-rate 2 --run-time 2m --headless
```

**Expected Results**:
- P95 response time: < 200ms
- Failure rate: 0%
- RPS: 50-100

### 2. Peak Load Test

**Goal**: Test system under expected peak load

```bash
locust -f tests/locustfile.py --host=http://localhost:8000 \
  --users 100 --spawn-rate 10 --run-time 5m --headless
```

**Expected Results**:
- P95 response time: < 500ms
- Failure rate: < 1%
- RPS: 200-500

### 3. Stress Test

**Goal**: Find breaking point of the system

```bash
locust -f tests/locustfile.py --host=http://localhost:8000 \
  --users 500 --spawn-rate 50 --run-time 10m --headless
```

**Monitor**: When does the system start failing? At what user count?

### 4. Endurance Test

**Goal**: Test for memory leaks and resource exhaustion

```bash
locust -f tests/locustfile.py --host=http://localhost:8000 \
  --users 50 --spawn-rate 5 --run-time 30m --headless
```

**Monitor**: Are response times stable over 30 minutes, or do they gradually increase?

## Test Workflows Covered

The locustfile includes these realistic workflows:

1. **AuthenticationFlow**:
   - User registration
   - Token refresh
   - Profile retrieval

2. **WorkoutPlanWorkflow** (most common):
   - Get daily plan (3x weight)
   - Save daily plan (2x weight)
   - Get weekly plan (2x weight)
   - Save weekly plan (1x weight)

3. **HealthDataWorkflow**:
   - Ingest health samples (3x weight) - simulates wearable device sync
   - Get readiness score (2x weight)
   - List health samples (1x weight)

4. **MealsWorkflow**:
   - Get weekly meal plan

## Performance Optimization Tips

If you identify bottlenecks:

1. **Slow Database Queries**:
   - Add database indexes on frequently queried columns
   - Use connection pooling
   - Consider read replicas for heavy read workloads

2. **High CPU Usage**:
   - Profile code with `py-spy` to find hot spots
   - Add caching for expensive computations
   - Optimize algorithms

3. **Memory Issues**:
   - Check for memory leaks with `memory_profiler`
   - Limit result set sizes
   - Use pagination for large queries

4. **Network Bottlenecks**:
   - Enable response compression (gzip)
   - Implement HTTP caching headers
   - Use CDN for static assets

## Monitoring During Load Tests

While load tests run, monitor these system metrics:

```bash
# CPU and memory usage
htop

# Database connections (if using PostgreSQL)
psql -c "SELECT count(*) FROM pg_stat_activity;"

# API logs for errors
tail -f logs/app.log | grep ERROR

# View Prometheus metrics
curl http://localhost:8000/metrics
```

## Continuous Load Testing

For CI/CD integration, add this to GitHub Actions:

```yaml
- name: Run Load Tests
  run: |
    source .venv/bin/activate
    uvicorn main:app &
    sleep 5
    locust -f tests/locustfile.py --host=http://localhost:8000 \
      --users 50 --spawn-rate 10 --run-time 1m --headless \
      --only-summary
```

## Next Steps

After completing load tests:

1. Document baseline performance metrics in `PERFORMANCE_BASELINE.md`
2. Set up performance monitoring dashboards (Grafana + Prometheus)
3. Create alerts for performance degradation
4. Run load tests before each major release
5. Compare performance across releases to catch regressions
