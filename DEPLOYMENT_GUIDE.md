# Deployment Guide - Staging Environment

## Overview
This guide covers deploying Artemis and all supporting services to the staging environment.

## Prerequisites

### 1. AWS Access
- AWS CLI configured with appropriate credentials
- Access to `staging` environment in AWS
- IAM role with permissions for ECS, ECR, Secrets Manager

### 2. GitHub Access
- Access to `rummel-tech/infrastructure` repository
- Access to `rummel-tech/services` repository
- `PAT_TOKEN` secret configured in GitHub
- `AWS_ROLE_TO_ASSUME` secret configured in GitHub

### 3. Infrastructure
The following infrastructure must exist (created via Terraform):
- VPC with subnets
- ECS Cluster: `staging-cluster`
- RDS PostgreSQL database (for staging)
- ALB (Application Load Balancer)
- ECS Services for each application
- CloudWatch log groups
- AWS Secrets Manager secrets

## Services to Deploy

| Service | Port | Database | Dependencies |
|---------|------|----------|--------------|
| auth | 8090 | PostgreSQL | none |
| workout-planner | 8000 | PostgreSQL | common |
| home-manager | 8020 | PostgreSQL | common |
| vehicle-manager | 8030 | PostgreSQL | common |
| meal-planner | 8010 | PostgreSQL | common, workout-planner (optional) |
| work-planner | 8040 | PostgreSQL | common |
| education-planner | 8050 | PostgreSQL | common |
| content-planner | 8060 | PostgreSQL | common |
| artemis | 8080 | N/A (Gateway) | auth + all module services |

## Pre-Deployment Steps

### 1. Run Pre-Flight Checks

```bash
cd <repo-root>/services
chmod +x deployment-preflight.sh
./deployment-preflight.sh
```

This validates:
- All Dockerfiles exist and are properly configured
- Python syntax is valid
- Common package is referenced correctly
- Service ports are correct
- Module integrations are in place

### 2. Ensure Terraform Infrastructure Exists

If infrastructure hasn't been created yet:

```bash
cd <infrastructure-repo>/terraform

# Initialize Terraform
terraform init

# Plan the deployment
terraform plan -var-file=environments/staging.tfvars -out=staging.tfplan

# Apply (creates all infrastructure)
terraform apply staging.tfplan
```

This creates:
- ECS Cluster and Services
- RDS Database
- Application Load Balancer
- Security Groups
- IAM Roles
- CloudWatch Logs

### 3. Configure Database Secrets

Each module service needs a `DATABASE_URL` secret in AWS Secrets Manager:

```bash
# Get the RDS endpoint from Terraform output
DB_ENDPOINT=$(cd <infrastructure-repo>/terraform && terraform output -raw db_endpoint)

# Format: postgresql://username:password@endpoint:5432/dbname
DATABASE_URL="postgresql://admin:YOUR_PASSWORD@${DB_ENDPOINT}:5432/artemis"

# Create secrets for each service
for svc in workout-planner home-manager vehicle-manager meal-planner work-planner education-planner content-planner; do
  aws secretsmanager create-secret \
    --name "staging/${svc}/database_url" \
    --secret-string "$DATABASE_URL" \
    --region us-east-1
done

# auth and artemis don't need a DATABASE_URL secret
```

### 4. Run Database Migrations

After first deployment, run migrations to create tables:

```bash
# Connect to staging database
psql "$DATABASE_URL"

# Or run migrations via ECS exec (after containers are running):
aws ecs execute-command \
  --cluster staging-cluster \
  --task <TASK_ID> \
  --container staging-home-manager \
  --command "python migrate_db.py" \
  --interactive
```

## Deployment Methods

### Method 1: GitHub Actions (Recommended)

All services are deployed from a single workflow in the `services` repository:

```bash
# Deploy a specific service
gh workflow run deploy-services.yml \
  --repo rummel-tech/services \
  -f service=home-manager \
  -f environment=staging

# Deploy all services (push to main triggers automatic detection)
git push origin main
```

The workflow (`services/.github/workflows/deploy-services.yml`) auto-detects which services changed on push to `main` and only deploys those. To force-deploy a specific service use `workflow_dispatch` with the `service` input.

Available service inputs: `auth`, `workout-planner`, `home-manager`, `vehicle-manager`, `meal-planner`, `work-planner`, `education-planner`, `content-planner`, `artemis`

### Method 2: Deploy All Services Script

```bash
#!/bin/bash
# Deploy all services in dependency order
SERVICES=("auth" "workout-planner" "home-manager" "vehicle-manager" "meal-planner" "work-planner" "education-planner" "content-planner" "artemis")

for service in "${SERVICES[@]}"; do
    echo "Deploying $service to staging..."
    gh workflow run deploy-services.yml \
      --repo rummel-tech/services \
      -f service=$service \
      -f environment=staging
    sleep 15
done
```

## Deployment Order

**IMPORTANT**: Deploy in this order to ensure dependencies are available:

1. **auth** (required by all services for token verification)
2. **workout-planner** (standalone module)
3. **home-manager** (standalone module)
4. **vehicle-manager** (standalone module)
5. **meal-planner** (optionally consumes workout-planner data)
6. **work-planner** (standalone module)
7. **education-planner** (standalone module)
8. **content-planner** (standalone module)
9. **artemis** (gateway — depends on auth + all module services)

## Post-Deployment Validation

### 1. Check ECS Service Status

```bash
# Check all services
aws ecs describe-services \
  --cluster staging-cluster \
  --services staging-auth-service staging-workout-planner-service staging-home-manager-service staging-vehicle-manager-service staging-meal-planner-service staging-work-planner-service staging-education-planner-service staging-content-planner-service staging-artemis-service \
  --region us-east-1 \
  --query 'services[*].[serviceName,status,runningCount,desiredCount]' \
  --output table
```

### 2. View Logs

```bash
# Individual service logs (replace <service> with: auth, workout-planner, home-manager, vehicle-manager, meal-planner, artemis)
aws logs tail /ecs/staging-<service> --follow --region us-east-1
```

### 3. Test Health Endpoints

Get the ALB DNS name:
```bash
ALB_DNS=$(cd <infrastructure-repo>/terraform && terraform output -raw alb_dns_name)
```

Health and readiness endpoints are unauthenticated:
```bash
curl http://${ALB_DNS}/auth/health
curl http://${ALB_DNS}/workout-planner/health
curl http://${ALB_DNS}/home-manager/health
curl http://${ALB_DNS}/vehicle-manager/health
curl http://${ALB_DNS}/meal-planner/health
curl http://${ALB_DNS}/work-planner/health
curl http://${ALB_DNS}/education-planner/health
curl http://${ALB_DNS}/content-planner/health
curl http://${ALB_DNS}/artemis/health
# All should return: {"status":"healthy","service":"<name>"}
```

### 4. Test Artemis Integration

All data endpoints require a valid JWT. Obtain a token from the auth service first:
```bash
TOKEN=$(curl -s -X POST http://${ALB_DNS}/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"test@example.com","password":"..."}' | jq -r '.access_token')

# Get Artemis dashboard
curl -H "Authorization: Bearer $TOKEN" http://${ALB_DNS}/artemis/dashboard/summary
```

### 5. Test Module Manifests

Manifests are unauthenticated — verify all modules registered correctly:
```bash
for svc in workout-planner home-manager vehicle-manager meal-planner work-planner education-planner content-planner; do
  echo "=== $svc ==="
  curl -s http://${ALB_DNS}/${svc}/artemis/manifest | jq '.module.id'
done
```

## Troubleshooting

### Service Won't Start

Check logs:
```bash
aws logs tail /ecs/staging-<service-name> --follow --region us-east-1
```

Common issues:
- Missing DATABASE_URL secret
- Database connection failure
- Port conflicts
- Missing common package

### Database Connection Issues

Verify secret exists:
```bash
aws secretsmanager get-secret-value \
  --secret-id staging/<service-name>/database_url \
  --region us-east-1
```

Test connection from ECS:
```bash
aws ecs execute-command \
  --cluster staging-cluster \
  --task <TASK_ID> \
  --container staging-<service-name> \
  --command "python -c 'from common.database import get_database_url; print(get_database_url())'" \
  --interactive
```

### Artemis Can't Connect to Backend Services

1. Check service discovery/DNS
2. Verify security groups allow communication
3. Check environment variables in Artemis:
```bash
aws ecs describe-task-definition \
  --task-definition staging-artemis \
  --query 'taskDefinition.containerDefinitions[0].environment'
```

4. Update Artemis environment variables if needed:
```bash
# Set backend service URLs (env vars injected via ECS task definition / Terraform)
WORKOUT_PLANNER_URL=http://staging-workout-planner.local:8000
HOME_MANAGER_URL=http://staging-home-manager.local:8020
VEHICLE_MANAGER_URL=http://staging-vehicle-manager.local:8030
MEAL_PLANNER_URL=http://staging-meal-planner.local:8010
ARTEMIS_AUTH_URL=http://staging-auth.local:8090
```

### Docker Build Failures

Common issues:
- Missing common package reference in Dockerfile
- Wrong PYTHONPATH
- Missing dependencies in requirements.txt

Test locally:
```bash
cd <repo-root>/services
docker build -f home-manager/Dockerfile -t test-home-manager .
docker run -p 8020:8020 -e DATABASE_URL=sqlite:///./test.db test-home-manager
```

## Rollback Procedure

If deployment fails, rollback to previous version:

```bash
# Get previous task definition revision
aws ecs describe-task-definition \
  --task-definition staging-<service-name> \
  --query 'taskDefinition.revision' \
  --output text

# Rollback to previous revision (e.g., revision 5)
aws ecs update-service \
  --cluster staging-cluster \
  --service staging-<service-name>-service \
  --task-definition staging-<service-name>:5 \
  --region us-east-1
```

## Monitoring

### CloudWatch Dashboards

View metrics at:
```
https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=staging-services
```

Key metrics:
- CPU utilization
- Memory utilization
- Request count
- Error rate
- Response time

### Alarms

Configured alarms will notify: `alerts@example.com`

Update in `staging.tfvars`:
```hcl
alert_email = "your-email@example.com"
```

## Cost Optimization

Staging environment is configured for cost savings:
- **CPU**: 256 (vs 512 in production)
- **Memory**: 512 MB (vs 1024 MB in production)
- **Instances**: 1 (vs 2+ in production)
- **NAT Gateway**: Single (vs per-AZ in production)
- **Database**: db.t3.micro (vs db.t3.small in production)
- **Log Retention**: 7 days (vs 30 in production)

Estimated monthly cost: ~$50-100

## Next Steps

After successful staging deployment:

1. **Integration Testing**: Run full test suite against staging
2. **Performance Testing**: Load test each service
3. **Security Scan**: Run security scans on deployed images
4. **Documentation**: Update API documentation
5. **Production Deployment**: Follow same process for production environment

## Support

For issues:
1. Check CloudWatch logs
2. Review deployment workflow runs in GitHub Actions
3. Verify Terraform state
4. Contact DevOps team
