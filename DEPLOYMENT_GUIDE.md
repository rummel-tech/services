# Deployment Guide - Staging Environment

## Overview
This guide covers deploying Artemis and all supporting services (home-manager, vehicle-manager, meal-planner) to the staging environment.

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
| artemis | 8000 | N/A (Gateway) | home-manager, vehicle-manager, meal-planner |
| home-manager | 8020 | PostgreSQL | common |
| vehicle-manager | 8030 | PostgreSQL | common |
| meal-planner | 8010 | PostgreSQL | common |

## Pre-Deployment Steps

### 1. Run Pre-Flight Checks

```bash
cd /home/shawn/_Projects/services
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
cd /home/shawn/_Projects/infrastructure/terraform

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

Each service needs a `DATABASE_URL` secret in AWS Secrets Manager:

```bash
# Get the RDS endpoint from Terraform output
DB_ENDPOINT=$(cd /home/shawn/_Projects/infrastructure/terraform && terraform output -raw db_endpoint)

# Format: postgresql://username:password@endpoint:5432/dbname
DATABASE_URL="postgresql://admin:YOUR_PASSWORD@${DB_ENDPOINT}:5432/artemis"

# Create secrets for each service
aws secretsmanager create-secret \
  --name staging/home-manager/database_url \
  --secret-string "$DATABASE_URL" \
  --region us-east-1

aws secretsmanager create-secret \
  --name staging/vehicle-manager/database_url \
  --secret-string "$DATABASE_URL" \
  --region us-east-1

aws secretsmanager create-secret \
  --name staging/meal-planner/database_url \
  --secret-string "$DATABASE_URL" \
  --region us-east-1

# Artemis doesn't need database (it's a gateway)
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

Deploy via GitHub Actions workflow dispatch:

#### Deploy Home Manager
```bash
# Navigate to GitHub
# Go to: infrastructure/.github/workflows/deploy-home-manager-backend.yml
# Click "Run workflow"
# Select:
#   - environment: staging
#   - repo_ref: main
```

Or via `gh` CLI:
```bash
gh workflow run deploy-home-manager-backend.yml \
  --repo rummel-tech/infrastructure \
  -f environment=staging \
  -f repo_ref=main
```

#### Deploy Vehicle Manager
```bash
gh workflow run deploy-vehicle-manager-backend.yml \
  --repo rummel-tech/infrastructure \
  -f environment=staging \
  -f repo_ref=main
```

#### Deploy Meal Planner
```bash
gh workflow run deploy-meal-planner-backend.yml \
  --repo rummel-tech/infrastructure \
  -f environment=staging \
  -f repo_ref=main
```

#### Deploy Artemis
```bash
gh workflow run deploy-artemis-backend.yml \
  --repo rummel-tech/infrastructure \
  -f environment=staging \
  -f repo_ref=main
```

### Method 2: Manual Deploy via Reusable Workflow

```bash
# Deploy all services in order
gh workflow run deploy-backend.yml \
  --repo rummel-tech/infrastructure \
  -f app_name=home-manager \
  -f environment=staging \
  -f repo_ref=main

gh workflow run deploy-backend.yml \
  --repo rummel-tech/infrastructure \
  -f app_name=vehicle-manager \
  -f environment=staging \
  -f repo_ref=main

gh workflow run deploy-backend.yml \
  --repo rummel-tech/infrastructure \
  -f app_name=meal-planner \
  -f environment=staging \
  -f repo_ref=main

gh workflow run deploy-backend.yml \
  --repo rummel-tech/infrastructure \
  -f app_name=artemis \
  -f environment=staging \
  -f repo_ref=main
```

### Method 3: Deploy All Services Script

Create a batch deployment script:

```bash
#!/bin/bash
# deploy-all-staging.sh

SERVICES=("home-manager" "vehicle-manager" "meal-planner" "artemis")

for service in "${SERVICES[@]}"; do
    echo "Deploying $service to staging..."
    gh workflow run deploy-backend.yml \
      --repo rummel-tech/infrastructure \
      -f app_name=$service \
      -f environment=staging \
      -f repo_ref=main

    echo "Waiting 30 seconds before next deployment..."
    sleep 30
done

echo "All deployments triggered!"
```

## Deployment Order

**IMPORTANT**: Deploy in this order to ensure dependencies are available:

1. **home-manager** (required by artemis assets module)
2. **vehicle-manager** (required by artemis assets module)
3. **meal-planner** (required by artemis nutrition module)
4. **artemis** (depends on all above services)

## Post-Deployment Validation

### 1. Check ECS Service Status

```bash
# Check all services
aws ecs describe-services \
  --cluster staging-cluster \
  --services staging-home-manager-service staging-vehicle-manager-service staging-meal-planner-service staging-artemis-service \
  --region us-east-1 \
  --query 'services[*].[serviceName,status,runningCount,desiredCount]' \
  --output table
```

### 2. View Logs

```bash
# Home Manager logs
aws logs tail /ecs/staging-home-manager --follow --region us-east-1

# Vehicle Manager logs
aws logs tail /ecs/staging-vehicle-manager --follow --region us-east-1

# Meal Planner logs
aws logs tail /ecs/staging-meal-planner --follow --region us-east-1

# Artemis logs
aws logs tail /ecs/staging-artemis --follow --region us-east-1
```

### 3. Test Health Endpoints

Get the ALB DNS name:
```bash
ALB_DNS=$(cd /home/shawn/_Projects/infrastructure/terraform && terraform output -raw alb_dns_name)
```

Test each service:
```bash
# Home Manager
curl http://${ALB_DNS}/home-manager/health
# Expected: {"status":"healthy","service":"home-manager"}

# Vehicle Manager
curl http://${ALB_DNS}/vehicle-manager/health
# Expected: {"status":"healthy","service":"vehicle-manager"}

# Meal Planner
curl http://${ALB_DNS}/meal-planner/health
# Expected: {"status":"healthy","service":"meal-planner"}

# Artemis
curl http://${ALB_DNS}/artemis/health
# Expected: {"status":"healthy"}
```

### 4. Test Artemis Integration

```bash
# Get Artemis dashboard
curl http://${ALB_DNS}/artemis/dashboard/summary

# Expected: JSON with module summaries including:
# - nutrition module showing meal-planner data
# - assets module showing home-manager + vehicle-manager data
```

### 5. Test Database Connectivity

```bash
# Create a test asset via home-manager
curl -X POST http://${ALB_DNS}/home-manager/assets \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "name": "Test Item",
    "asset_type": "home",
    "category": "appliance",
    "condition": "good"
  }'

# List assets
curl http://${ALB_DNS}/home-manager/assets/test_user

# Verify Artemis can see it
curl http://${ALB_DNS}/artemis/dashboard/summary
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
# Set backend service URLs
SERVICE_HOME_MANAGER_URL=http://staging-home-manager.local:8020
SERVICE_VEHICLE_MANAGER_URL=http://staging-vehicle-manager.local:8030
SERVICE_MEAL_PLANNER_URL=http://staging-meal-planner.local:8010
```

### Docker Build Failures

Common issues:
- Missing common package reference in Dockerfile
- Wrong PYTHONPATH
- Missing dependencies in requirements.txt

Test locally:
```bash
cd /home/shawn/_Projects/services
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
