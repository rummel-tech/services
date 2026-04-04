#!/bin/bash
# Deploy all services to staging environment in correct order

set -e

echo "============================================================"
echo "  STAGING DEPLOYMENT"
echo "============================================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
REPO="rummel-tech/infrastructure"
ENVIRONMENT="staging"
REF="main"

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "Error: GitHub CLI (gh) is not installed"
    echo "Install with: brew install gh (macOS) or see https://cli.github.com/"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "Error: Not authenticated with GitHub CLI"
    echo "Run: gh auth login"
    exit 1
fi

echo -e "${BLUE}Repository:${NC} $REPO"
echo -e "${BLUE}Environment:${NC} $ENVIRONMENT"
echo -e "${BLUE}Branch/Ref:${NC} $REF"
echo ""

# Run pre-flight checks
echo -e "${YELLOW}Running pre-flight checks...${NC}"
if ./deployment-preflight.sh; then
    echo -e "${GREEN}✓ Pre-flight checks passed${NC}"
else
    echo "Pre-flight checks failed. Aborting deployment."
    exit 1
fi
echo ""

# Services to deploy in order (auth first, modules second, artemis last)
SERVICES=(
    "auth:8090"
    "workout-planner:8000"
    "meal-planner:8010"
    "home-manager:8020"
    "vehicle-manager:8030"
    "work-planner:8040"
    "education-planner:8050"
    "content-planner:8060"
    "artemis:8080"
)

echo "============================================================"
echo "  DEPLOYMENT ORDER"
echo "============================================================"
for service_port in "${SERVICES[@]}"; do
    service="${service_port%%:*}"
    port="${service_port##*:}"
    echo "  $service (port $port)"
done
echo ""

read -p "Deploy to staging? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

echo ""
echo "============================================================"
echo "  STARTING DEPLOYMENTS"
echo "============================================================"

for service_port in "${SERVICES[@]}"; do
    service="${service_port%%:*}"
    port="${service_port##*:}"

    echo ""
    echo "-----------------------------------------------------------"
    echo -e "${BLUE}Deploying: $service${NC}"
    echo "-----------------------------------------------------------"

    # Trigger workflow
    echo "Triggering deployment workflow..."
    gh workflow run deploy-backend.yml \
        --repo "$REPO" \
        -f app_name="$service" \
        -f environment="$ENVIRONMENT" \
        -f repo_ref="$REF"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Workflow triggered for $service${NC}"

        # Wait between deployments
        if [ "$service" != "artemis" ]; then
            echo "Waiting 60 seconds before next deployment..."
            sleep 60
        fi
    else
        echo "Failed to trigger workflow for $service"
        exit 1
    fi
done

echo ""
echo "============================================================"
echo "  DEPLOYMENT COMPLETE"
echo "============================================================"
echo ""
echo "All deployment workflows have been triggered!"
echo ""
echo "Next steps:"
echo "1. Monitor workflow runs:"
echo "   gh run list --repo $REPO --workflow=deploy-backend.yml"
echo ""
echo "2. View specific run:"
echo "   gh run view --repo $REPO <RUN_ID>"
echo ""
echo "3. Check service status (after ~5 minutes):"
echo "   aws ecs describe-services \\"
echo "     --cluster staging-cluster \\"
echo "     --services staging-auth-service staging-workout-planner-service staging-meal-planner-service staging-home-manager-service staging-vehicle-manager-service staging-work-planner-service staging-education-planner-service staging-content-planner-service staging-artemis-service \\"
echo "     --region us-east-1"
echo ""
echo "4. View logs:"
echo "   aws logs tail /ecs/staging-<service-name> --follow --region us-east-1"
echo ""
echo "5. Test health endpoints:"
echo "   curl http://<ALB_DNS>/auth/health"
echo "   curl http://<ALB_DNS>/workout-planner/health"
echo "   curl http://<ALB_DNS>/meal-planner/health"
echo "   curl http://<ALB_DNS>/home-manager/health"
echo "   curl http://<ALB_DNS>/vehicle-manager/health"
echo "   curl http://<ALB_DNS>/work-planner/health"
echo "   curl http://<ALB_DNS>/education-planner/health"
echo "   curl http://<ALB_DNS>/content-planner/health"
echo "   curl http://<ALB_DNS>/artemis/health"
echo ""
