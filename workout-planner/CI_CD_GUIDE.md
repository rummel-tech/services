# CI/CD Guide - Workout Planner Backend

This guide explains the Continuous Integration and Continuous Deployment (CI/CD) workflows for the Workout Planner backend.

## Overview

The backend has comprehensive CI/CD automation using GitHub Actions:

1. **Test Workflow** - Runs unit tests, integration tests, coverage analysis, and linting
2. **Security Workflow** - Performs static code analysis, dependency scanning, and container security scanning
3. **Deployment Workflow** - Builds and deploys Docker containers to AWS ECS

## Workflows

### 1. Test Workflow (`test-workout-planner-backend.yml`)

**Triggers:**
- Push to `main` branch
- Pull requests to `main` branch
- Manual trigger via `repository_dispatch`
- Manual trigger via workflow UI

**Jobs:**

#### Job 1: Unit Tests (`test`)
- Sets up Python 3.14
- Installs dependencies
- Runs all tests with coverage
- Generates coverage reports (XML and HTML)
- Checks coverage meets 55% threshold
- Comments on PR with test results

**Requirements:**
- Coverage must be ≥ 55%
- All tests must pass

#### Job 2: Integration Tests (`integration-tests`)
- Runs after unit tests pass
- Executes `tests/test_integration.py`
- Tests complete user workflows
- Verifies cross-module functionality

#### Job 3: Linting (`lint`)
- **Black**: Code formatting check
- **isort**: Import sorting verification
- **flake8**: Style guide enforcement

**Artifacts:**
- Coverage reports (XML + HTML)
- Retention: 30 days

### 2. Security Workflow (`security-scan-workout-planner.yml`)

**Triggers:**
- Push to `main` branch
- Pull requests to `main` branch
- Weekly schedule (Mondays at 9 AM UTC)
- Manual trigger

**Jobs:**

#### Job 1: Bandit Scan (`bandit-scan`)
- Static code analysis for security vulnerabilities
- Scans all Python files
- Excludes tests, virtual environments, and dependencies
- Skips B101 (assert_used in tests)

**Severity Levels:**
- **High**: Fails the build
- **Medium**: Warning, does not fail
- **Low**: Informational

**Artifacts:**
- `bandit-report.json`
- Retention: 90 days

#### Job 2: Dependency Scan (`dependency-scan`)
- Uses Safety to check for known vulnerabilities
- Scans all installed packages
- Generates JSON report

**Note**: Known vulnerabilities in `ecdsa` (via `python-jose`) are documented in `SECURITY_REPORT.md` and accepted as low-risk. These do not fail the build.

**Artifacts:**
- `safety-report.json`
- Retention: 90 days

#### Job 3: Security Summary (`security-summary`)
- Aggregates results from Bandit and Safety
- Creates consolidated security report
- Comments on PRs with security findings

#### Job 4: Container Scan (`container-scan`)
- Builds Docker image
- Scans with Trivy for container vulnerabilities
- Checks for HIGH and CRITICAL severity issues
- Uploads results to GitHub Security tab (SARIF format)

**Artifacts:**
- `trivy-report.json`
- SARIF results (viewable in GitHub Security tab)
- Retention: 30 days

### 3. Deployment Workflow (`deploy-workout-planner-backend.yml`)

**Triggers:**
- Manual trigger via `repository_dispatch`
- Manual trigger via workflow UI

**Process:**
1. Checkout infrastructure and app repos
2. Configure AWS credentials via OIDC
3. Ensure ECR repository exists
4. Build Docker image
5. Push image to Amazon ECR with tags:
   - `${GITHUB_SHA}` (commit-specific)
   - `latest`

**Deployment Note**: The workflow pushes the container image but does not automatically deploy to ECS. Manual ECS task definition updates are required.

## Running Workflows Locally

### Running Tests

```bash
cd /home/shawn/APP_DEV/workout-planner/applications/backend/python_fastapi_server

# Activate virtual environment
source .venv/bin/activate

# Run all tests with coverage
pytest tests/ --cov=. --cov-report=term --cov-report=html -v

# Run only unit tests
pytest tests/ -k "not integration" -v

# Run only integration tests
pytest tests/test_integration.py -v

# Run specific test file
pytest tests/test_auth.py -v
```

### Running Security Scans

```bash
# Install security tools
pip install bandit safety

# Run Bandit
bandit -r . -x ./.venv,./tests --skip B101 -f json -o bandit-report.json

# Run Safety
safety check --json --output safety-report.json

# View Bandit report
cat bandit-report.json | python -m json.tool | less

# View Safety report
cat safety-report.json | python -m json.tool | less
```

### Running Linters

```bash
# Install linting tools
pip install black isort flake8

# Check code formatting (Black)
black --check --diff .

# Auto-fix code formatting
black .

# Check import sorting (isort)
isort --check-only --diff .

# Auto-fix import sorting
isort .

# Run flake8
flake8 . --exclude=.venv,htmlcov,__pycache__
```

## Triggering Workflows from CLI

### Using GitHub CLI (`gh`)

```bash
# Trigger test workflow
gh workflow run test-workout-planner-backend.yml \
  --ref main \
  --repo srummel/infrastructure

# Trigger security scan
gh workflow run security-scan-workout-planner.yml \
  --ref main \
  --repo srummel/infrastructure

# Trigger deployment
gh workflow run deploy-workout-planner-backend.yml \
  --ref main \
  --repo srummel/infrastructure
```

### Using repository_dispatch

```bash
# Trigger test workflow via API
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/repos/srummel/infrastructure/dispatches \
  -d '{"event_type":"test-workout-planner-backend","client_payload":{"ref":"main"}}'
```

## Understanding Build Status

### ✅ All Checks Passed

- All tests passed (57 tests)
- Coverage ≥ 55%
- No high-severity security issues
- Code formatting correct

**Action**: Safe to merge PR or deploy

### ⚠️ Warnings Present

- Medium/low security findings
- Coverage slightly below target
- Minor linting issues

**Action**: Review warnings, consider addressing before merge

### ❌ Build Failed

Common failure reasons:

1. **Test Failures**
   - Check test output in workflow logs
   - Reproduce locally: `pytest tests/ -v`
   - Fix failing tests and push again

2. **Coverage Below Threshold**
   - Current threshold: 55%
   - Add more tests to increase coverage
   - Or adjust threshold in workflow (not recommended)

3. **High Severity Security Issue**
   - Review Bandit report in artifacts
   - Address security vulnerabilities
   - See `SECURITY_REPORT.md` for guidance

4. **Linting Failures**
   - Run `black .` to auto-format
   - Run `isort .` to fix imports
   - Fix flake8 issues manually

## Coverage Requirements

**Current Coverage**: 61%
**Minimum Threshold**: 55%
**Target**: 80%

### Coverage by Module

| Module | Coverage |
|--------|----------|
| routers/meals.py | 100% |
| routers/readiness.py | 100% |
| tests/*.py | 98-99% |
| auth_service.py | 91% |
| routers/weekly_plans.py | 89% |
| routers/auth.py | 87% |
| routers/daily_plans.py | 77% |
| main.py | 77% |
| routers/health.py | 66% |

**Areas Needing More Tests:**
- `routers/goals.py` (27%)
- `routers/chat.py` (27%)
- `routers/strength.py` (37%)
- `routers/murph.py` (36%)
- `swim.py` (20%)

## Viewing CI/CD Results

### On GitHub

1. **Actions Tab**
   - View workflow runs
   - See logs for each job
   - Download artifacts

2. **Pull Requests**
   - Status checks at bottom of PR
   - Click "Details" to view logs
   - Automated comments with results

3. **Security Tab**
   - View Trivy scan results (SARIF)
   - See dependency alerts (Dependabot)

### Downloading Artifacts

```bash
# Using GitHub CLI
gh run list --repo srummel/infrastructure
gh run download <run_id> --repo srummel/infrastructure

# Or download from GitHub UI
# Actions → Select workflow run → Artifacts section
```

## Best Practices

### For Developers

1. **Run Tests Locally Before Pushing**
   ```bash
   pytest tests/ --cov=. --cov-report=term
   ```

2. **Fix Linting Issues Before Committing**
   ```bash
   black . && isort . && flake8 .
   ```

3. **Check Coverage After Adding Features**
   ```bash
   pytest tests/ --cov=. --cov-report=html
   # Open htmlcov/index.html to view coverage
   ```

4. **Review Security Findings**
   - Check `SECURITY_REPORT.md` for known issues
   - Address new high-severity findings immediately

### For Reviewers

1. **Check CI Status Before Approving**
   - All workflows must pass
   - Coverage should not decrease
   - No new high-severity security issues

2. **Review Test Changes**
   - New features should have tests
   - Bug fixes should have regression tests
   - Tests should be meaningful, not just for coverage

3. **Security Review**
   - Download and review security artifacts
   - Check for new vulnerabilities
   - Verify security best practices

## Troubleshooting

### Workflow Not Triggering

**Problem**: Push to main doesn't trigger workflow

**Solutions**:
- Check workflow file is in `.github/workflows/`
- Verify `paths` filter includes your changes
- Check GitHub Actions are enabled for repo
- Trigger manually via workflow UI

### Tests Pass Locally But Fail in CI

**Common Causes**:
1. **Environment Differences**
   - Check Python version matches (3.14)
   - Verify dependencies in requirements.txt

2. **Database Issues**
   - CI uses SQLite for tests
   - Check DATABASE_URL in test setup

3. **Timing Issues**
   - Tests may be order-dependent
   - Add proper test isolation (function-scoped fixtures)

4. **File Path Issues**
   - Use absolute paths or Path objects
   - Avoid hardcoded paths

### Artifact Not Available

**Problem**: Coverage reports or security scans missing

**Solutions**:
- Check workflow completed successfully
- Artifacts expire after retention period (30-90 days)
- Re-run workflow to regenerate artifacts

### Permission Errors in Workflow

**Problem**: Workflow can't comment on PR or upload SARIF

**Solutions**:
- Check `permissions` in workflow file
- Verify repo settings allow workflow permissions
- For SARIF upload, ensure Security tab is enabled

## Maintenance

### Updating Python Version

1. Update workflow files:
   ```yaml
   PYTHON_VERSION: '3.14'  # Change to new version
   ```

2. Update Dockerfile:
   ```dockerfile
   FROM python:3.14-slim
   ```

3. Test locally with new Python version

4. Update documentation

### Updating Dependencies

1. Update `requirements.txt`
2. Run security scan: `safety check`
3. Run tests: `pytest tests/`
4. Push and verify CI passes

### Adding New Workflows

1. Create workflow file in `.github/workflows/`
2. Use existing workflows as templates
3. Test with `repository_dispatch` or manual trigger
4. Document in this guide

## Integration with Other Tools

### Slack Notifications (Optional)

Add Slack notification step to workflows:

```yaml
- name: Notify Slack
  if: failure()
  uses: slackapi/slack-github-action@v1
  with:
    payload: |
      {
        "text": "❌ ${{ github.workflow }} failed"
      }
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```

### Code Coverage Services (Optional)

Upload coverage to Codecov or Coveralls:

```yaml
- name: Upload coverage to Codecov
  uses: codecov/codecov-action@v4
  with:
    files: ./coverage.xml
    flags: unittests
```

### Dependabot (Recommended)

Enable Dependabot for automatic dependency updates:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/applications/backend/python_fastapi_server"
    schedule:
      interval: "weekly"
```

---

## Quick Reference

### Common Commands

```bash
# Run all tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=. --cov-report=term

# Run integration tests only
pytest tests/test_integration.py -v

# Format code
black . && isort .

# Security scan
bandit -r . -x ./.venv,./tests --skip B101

# Dependency check
safety check

# Trigger workflow
gh workflow run test-workout-planner-backend.yml --ref main
```

### Coverage Targets

- ✅ **Current**: 61%
- ⚠️ **Minimum**: 55%
- 🎯 **Target**: 80%

### CI/CD Files

- `/home/shawn/APP_DEV/infrastructure/.github/workflows/test-workout-planner-backend.yml`
- `/home/shawn/APP_DEV/infrastructure/.github/workflows/security-scan-workout-planner.yml`
- `/home/shawn/APP_DEV/infrastructure/.github/workflows/deploy-workout-planner-backend.yml`

### Documentation

- `SECURITY_REPORT.md` - Security findings and recommendations
- `LOAD_TESTING.md` - Load testing guide
- `CI_CD_GUIDE.md` - This file

---

**Last Updated**: 2025-11-20
**Next Review**: 2025-12-20
