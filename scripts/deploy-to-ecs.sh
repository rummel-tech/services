#!/bin/bash
set -e

# Deploy services to AWS ECS
# Usage: ./deploy-to-ecs.sh [service-name] [aws-region]
# Example: ./deploy-to-ecs.sh meal-planner us-east-1
# Example: ./deploy-to-ecs.sh all us-east-1

SERVICE_NAME="${1:-all}"
AWS_REGION="${2:-us-east-1}"
ECS_CLUSTER="app-cluster"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Service configurations
declare -A SERVICE_PORTS=(
    ["meal-planner"]=8010
    ["home-manager"]=8020
    ["vehicle-manager"]=8030
    ["workout-planner"]=8000
)

deploy_service() {
    local service=$1
    local port=${SERVICE_PORTS[$service]}

    echo "=========================================="
    echo "Deploying $service on port $port"
    echo "=========================================="

    # Create ECR repository if it doesn't exist
    echo "Ensuring ECR repository exists..."
    aws ecr describe-repositories --repository-names "$service" --region "$AWS_REGION" >/dev/null 2>&1 || \
    aws ecr create-repository --repository-name "$service" --image-scanning-configuration scanOnPush=true --region "$AWS_REGION"

    # Login to ECR
    echo "Logging in to ECR..."
    aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

    # Build Docker image
    echo "Building Docker image..."
    cd "$(dirname "$0")/.."
    docker build -f "$service/Dockerfile" -t "$ECR_REGISTRY/$service:latest" .

    # Push to ECR
    echo "Pushing image to ECR..."
    docker push "$ECR_REGISTRY/$service:latest"

    # Register task definition
    echo "Registering ECS task definition..."
    TASK_DEF=$(cat <<EOF
{
    "family": "$service",
    "networkMode": "awsvpc",
    "requiresCompatibilities": ["FARGATE"],
    "cpu": "256",
    "memory": "512",
    "executionRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/ecsTaskExecutionRole",
    "containerDefinitions": [
        {
            "name": "$service",
            "image": "${ECR_REGISTRY}/${service}:latest",
            "essential": true,
            "portMappings": [
                {
                    "containerPort": $port,
                    "hostPort": $port,
                    "protocol": "tcp"
                }
            ],
            "healthCheck": {
                "command": ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:$port/health')\" || exit 1"],
                "interval": 30,
                "timeout": 5,
                "retries": 3,
                "startPeriod": 60
            },
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": "/ecs/$service",
                    "awslogs-region": "$AWS_REGION",
                    "awslogs-stream-prefix": "ecs",
                    "awslogs-create-group": "true"
                }
            },
            "environment": [
                {"name": "ENVIRONMENT", "value": "production"},
                {"name": "PORT", "value": "$port"}
            ]
        }
    ]
}
EOF
)

    echo "$TASK_DEF" > /tmp/task-def-${service}.json
    aws ecs register-task-definition --cli-input-json "file:///tmp/task-def-${service}.json" --region "$AWS_REGION"

    # Check if service exists
    SERVICE_EXISTS=$(aws ecs describe-services --cluster "$ECS_CLUSTER" --services "${service}-service" --region "$AWS_REGION" --query 'services[0].status' --output text 2>/dev/null || echo "MISSING")

    if [ "$SERVICE_EXISTS" == "ACTIVE" ]; then
        echo "Updating existing ECS service..."
        aws ecs update-service \
            --cluster "$ECS_CLUSTER" \
            --service "${service}-service" \
            --task-definition "$service" \
            --force-new-deployment \
            --region "$AWS_REGION"
    else
        echo "Creating new ECS service..."

        # Get default VPC and subnets
        VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query 'Vpcs[0].VpcId' --output text --region "$AWS_REGION")
        SUBNETS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query 'Subnets[*].SubnetId' --output text --region "$AWS_REGION" | tr '\t' ',')

        # Create security group if needed
        SG_NAME="${service}-sg"
        SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" --query 'SecurityGroups[0].GroupId' --output text --region "$AWS_REGION" 2>/dev/null || echo "None")

        if [ "$SG_ID" == "None" ] || [ -z "$SG_ID" ]; then
            echo "Creating security group..."
            SG_ID=$(aws ec2 create-security-group --group-name "$SG_NAME" --description "Security group for $service" --vpc-id "$VPC_ID" --region "$AWS_REGION" --query 'GroupId' --output text)
            aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port "$port" --cidr 0.0.0.0/0 --region "$AWS_REGION"
        fi

        aws ecs create-service \
            --cluster "$ECS_CLUSTER" \
            --service-name "${service}-service" \
            --task-definition "$service" \
            --desired-count 1 \
            --launch-type FARGATE \
            --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
            --region "$AWS_REGION"
    fi

    echo "✅ $service deployment initiated!"
    echo ""
}

# Ensure ECS cluster exists
echo "Ensuring ECS cluster exists..."
aws ecs describe-clusters --clusters "$ECS_CLUSTER" --region "$AWS_REGION" --query 'clusters[0].status' --output text 2>/dev/null || \
aws ecs create-cluster --cluster-name "$ECS_CLUSTER" --capacity-providers FARGATE FARGATE_SPOT --region "$AWS_REGION"

# Deploy services
if [ "$SERVICE_NAME" == "all" ]; then
    for service in "${!SERVICE_PORTS[@]}"; do
        deploy_service "$service"
    done
else
    if [ -z "${SERVICE_PORTS[$SERVICE_NAME]}" ]; then
        echo "Error: Unknown service '$SERVICE_NAME'"
        echo "Available services: ${!SERVICE_PORTS[@]}"
        exit 1
    fi
    deploy_service "$SERVICE_NAME"
fi

echo "=========================================="
echo "Deployment complete!"
echo "=========================================="
echo ""
echo "To check service status:"
echo "  aws ecs describe-services --cluster $ECS_CLUSTER --services <service>-service --region $AWS_REGION"
echo ""
echo "To get public IP:"
echo "  aws ecs list-tasks --cluster $ECS_CLUSTER --service-name <service>-service --region $AWS_REGION"
echo "  aws ecs describe-tasks --cluster $ECS_CLUSTER --tasks <task-arn> --region $AWS_REGION"
