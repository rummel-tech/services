# ✅ DEPLOYMENT READY - Staging Environment

## Summary
All services have been validated and are ready for deployment to the staging environment. Pipeline configurations, Dockerfiles, and infrastructure are properly configured.

## What Was Validated

### ✅ CI/CD Pipelines
- Reusable workflow: `deploy-backend.yml`
- Individual workflows for all services
- Proper AWS OIDC authentication
- ECR and ECS deployment configured
- Health checks implemented

### ✅ Dockerfiles Updated
All services now properly:
- Copy and use common package
- Set PYTHONPATH correctly
- Expose correct ports
- Install all dependencies

| Service | Dockerfile | Port | Status |
|---------|-----------|------|--------|
| artemis | ✅ Updated | 8000 | Ready |
| home-manager | ✅ Updated | 8020 | Ready |
| vehicle-manager | ✅ Updated | 8030 | Ready |
| meal-planner | ✅ Updated | 8010 | Ready |

### ✅ Terraform Configuration
- staging.tfvars validated
- All services enabled
- Cost-optimized settings
- Database configuration present

### ✅ Service Integration
- Artemis modules updated to proxy backends
- Common package shared across services
- Database migrations ready
- Python syntax validated

## Pre-Deployment Requirements

Before triggering deployment, ensure these exist:

### 1. Infrastructure (via Terraform)
```bash
cd /home/shawn/_Projects/infrastructure/terraform
terraform init
terraform plan -var-file=environments/staging.tfvars -out=staging.tfplan
terraform apply staging.tfplan
```

This creates:
- VPC, subnets, NAT gateway
- ECS cluster: `staging-cluster`
- RDS PostgreSQL database
- Application Load Balancer
- IAM roles
- Security groups

### 2. AWS Secrets (Manual Creation)
```bash
# Get database endpoint from Terraform
DB_ENDPOINT=$(cd /home/shawn/_Projects/infrastructure/terraform && terraform output -raw db_endpoint)
DATABASE_URL="postgresql://admin:YOUR_PASSWORD@${DB_ENDPOINT}:5432/artemis"

# Create secrets
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
```

### 3. GitHub Secrets (Repository Configuration)
Ensure these are set in `rummel-tech/infrastructure` repository:
- `PAT_TOKEN` - GitHub Personal Access Token with repo access
- `AWS_ROLE_TO_ASSUME` - AWS IAM Role ARN for OIDC authentication

## How to Deploy

### Option 1: Automated Script (Recommended)
```bash
cd /home/shawn/_Projects/services
./deploy-staging.sh
```

This will:
1. Run pre-flight checks
2. Prompt for confirmation
3. Deploy services in correct order
4. Wait between deployments
5. Provide monitoring commands

### Option 2: GitHub Actions UI
1. Go to https://github.com/rummel-tech/infrastructure/actions
2. Select workflow:
   - `Deploy Home Manager Backend`
   - `Deploy Vehicle Manager Backend`
   - `Deploy Meal Planner Backend`
   - `Deploy Artemis Backend`
3. Click "Run workflow"
4. Select:
   - Branch: `main`
   - Environment: `staging`

### Option 3: GitHub CLI
```bash
# Authenticate if needed
gh auth login

# Deploy in order
gh workflow run deploy-home-manager-backend.yml \
  --repo rummel-tech/infrastructure \
  -f environment=staging -f repo_ref=main

# Wait 2-3 minutes for home-manager to stabilize

gh workflow run deploy-vehicle-manager-backend.yml \
  --repo rummel-tech/infrastructure \
  -f environment=staging -f repo_ref=main

# Wait 2-3 minutes

gh workflow run deploy-meal-planner-backend.yml \
  --repo rummel-tech/infrastructure \
  -f environment=staging -f repo_ref=main

# Wait 2-3 minutes

gh workflow run deploy-artemis-backend.yml \
  --repo rummel-tech/infrastructure \
  -f environment=staging -f repo_ref=main
```

## Deployment Order (IMPORTANT)

Deploy in this order to ensure dependencies exist:
1. **home-manager** (8020)
2. **vehicle-manager** (8030)
3. **meal-planner** (8010)
4. **artemis** (8000) - depends on all above

## Post-Deployment Steps

### 1. Run Database Migrations
```bash
# Via ECS exec (requires session manager plugin)
aws ecs execute-command \
  --cluster staging-cluster \
  --task <TASK_ID> \
  --container staging-home-manager \
  --command "python migrate_db.py" \
  --interactive

# Repeat for vehicle-manager and meal-planner
```

Or connect directly to RDS:
```bash
psql "$DATABASE_URL" < home-manager/migrate_db.sql
```

### 2. Update Artemis Service URLs

After services are deployed, update Artemis environment variables to point to actual service endpoints:

```bash
# Get service discovery DNS names or use ALB targets
# Update task definition with:
SERVICE_HOME_MANAGER_URL=http://internal-staging-alb.us-east-1.elb.amazonaws.com/home-manager
SERVICE_VEHICLE_MANAGER_URL=http://internal-staging-alb.us-east-1.elb.amazonaws.com/vehicle-manager
SERVICE_MEAL_PLANNER_URL=http://internal-staging-alb.us-east-1.elb.amazonaws.com/meal-planner
SERVICE_WORKOUT_PLANNER_URL=http://internal-staging-alb.us-east-1.elb.amazonaws.com/workout-planner

# Then force new deployment
aws ecs update-service \
  --cluster staging-cluster \
  --service staging-artemis-service \
  --force-new-deployment \
  --region us-east-1
```

### 3. Verify Deployment
```bash
# Check all services are running
aws ecs describe-services \
  --cluster staging-cluster \
  --services \
    staging-home-manager-service \
    staging-vehicle-manager-service \
    staging-meal-planner-service \
    staging-artemis-service \
  --region us-east-1 \
  --query 'services[*].[serviceName,status,runningCount,desiredCount]' \
  --output table
```

Expected output:
```
--------------------------------------------------
|              DescribeServices                  |
+------------------------------------+--------+--+
|  staging-home-manager-service      | ACTIVE | 1| 1|
|  staging-vehicle-manager-service   | ACTIVE | 1| 1|
|  staging-meal-planner-service      | ACTIVE | 1| 1|
|  staging-artemis-service           | ACTIVE | 1| 1|
+------------------------------------+--------+--+
```

### 4. Test Health Endpoints
```bash
# Get ALB DNS name
ALB_DNS=$(cd /home/shawn/_Projects/infrastructure/terraform && terraform output -raw alb_dns_name)

# Test all services
curl http://${ALB_DNS}/home-manager/health
curl http://${ALB_DNS}/vehicle-manager/health
curl http://${ALB_DNS}/meal-planner/health
curl http://${ALB_DNS}/artemis/health
```

All should return HTTP 200 with health status.

### 5. Test Integration
```bash
# Create test data
curl -X POST http://${ALB_DNS}/home-manager/assets \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo_user",
    "name": "Test Appliance",
    "asset_type": "home",
    "category": "appliance",
    "condition": "good",
    "location": "Kitchen"
  }'

# Verify via Artemis
curl http://${ALB_DNS}/artemis/dashboard/summary
```

Should show asset count in AssetsModule summary.

## Monitoring

### View Logs
```bash
# Individual service logs
aws logs tail /ecs/staging-home-manager --follow --region us-east-1
aws logs tail /ecs/staging-vehicle-manager --follow --region us-east-1
aws logs tail /ecs/staging-meal-planner --follow --region us-east-1
aws logs tail /ecs/staging-artemis --follow --region us-east-1
```

### Watch Workflow Runs
```bash
# List recent runs
gh run list --repo rummel-tech/infrastructure --workflow=deploy-backend.yml --limit 10

# Watch specific run
gh run watch <RUN_ID> --repo rummel-tech/infrastructure

# View logs
gh run view <RUN_ID> --repo rummel-tech/infrastructure --log
```

## Rollback Procedure

If deployment fails:
```bash
# Get previous task definition revision
aws ecs describe-task-definition \
  --task-definition staging-<service-name> \
  --query 'taskDefinition.revision'

# Rollback
aws ecs update-service \
  --cluster staging-cluster \
  --service staging-<service-name>-service \
  --task-definition staging-<service-name>:<previous-revision> \
  --region us-east-1
```

## Troubleshooting

### Service Won't Start
1. Check logs: `aws logs tail /ecs/staging-<service> --follow`
2. Verify secrets exist: `aws secretsmanager get-secret-value --secret-id staging/<service>/database_url`
3. Check task definition: `aws ecs describe-task-definition --task-definition staging-<service>`

### Container Health Check Failing
- Verify port is correct in task definition
- Check security group allows ALB -> ECS traffic
- Ensure health endpoint returns 200
- Review application logs for startup errors

### Artemis Can't Connect to Backends
1. Verify service URLs are configured correctly
2. Check security groups allow inter-service communication
3. Verify backend services are running
4. Test backend health endpoints directly

## Success Criteria

✅ Deployment is successful when:
- [ ] All 4 ECS services show "ACTIVE" status
- [ ] All services have desired count = running count
- [ ] Health checks return HTTP 200
- [ ] CloudWatch logs show no errors
- [ ] Database tables exist (verify with psql)
- [ ] Artemis dashboard returns data
- [ ] Integration tests pass

## Files Created

Documentation:
- ✅ `DEPLOYMENT_GUIDE.md` - Comprehensive deployment guide
- ✅ `DEPLOYMENT_VALIDATION.md` - Validation checklist
- ✅ `DEPLOYMENT_READY.md` - This file
- ✅ `REFACTORING_SUMMARY.md` - Architecture changes

Scripts:
- ✅ `deployment-preflight.sh` - Pre-flight validation
- ✅ `deploy-staging.sh` - Automated deployment
- ✅ `test_refactoring.py` - Python import tests

Updated:
- ✅ `artemis/Dockerfile`
- ✅ `home-manager/Dockerfile`
- ✅ `vehicle-manager/Dockerfile`
- ✅ `meal-planner/Dockerfile`

## Estimated Costs

Staging environment monthly cost: **~$50-100**

Breakdown:
- ECS Fargate: ~$20-30 (4 services @ 256 CPU, 512 MB)
- RDS db.t3.micro: ~$15
- ALB: ~$20
- NAT Gateway: ~$30
- Data transfer: ~$5

## Support

For issues or questions:
1. Check deployment guide: `DEPLOYMENT_GUIDE.md`
2. Review logs in CloudWatch
3. Check GitHub Actions workflow runs
4. Verify Terraform state

## Next Steps

1. **Run Infrastructure**: `terraform apply` if not done
2. **Create Secrets**: Add DATABASE_URL to Secrets Manager
3. **Deploy Services**: Use one of the deployment methods above
4. **Run Migrations**: Create database tables
5. **Validate**: Run health checks and integration tests
6. **Monitor**: Watch logs and metrics

---

**Status**: ✅ READY FOR STAGING DEPLOYMENT

All preparation complete. Proceed with deployment using methods outlined above.
