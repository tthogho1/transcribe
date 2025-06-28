#!/bin/bash

# ECS Deployment Script for Transcribe Service
# Usage: ./deploy-to-ecs.sh [environment] [region]

set -e

# Default values
ENVIRONMENT=${1:-production}
AWS_REGION=${2:-ap-northeast-1}
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Configuration
ECR_REPOSITORY="transcribe-service"
IMAGE_TAG="latest"
CLUSTER_NAME="transcribe-cluster"
SERVICE_NAME="transcribe-service"
TASK_DEFINITION_FAMILY="transcribe-service"

echo "🚀 Starting ECS deployment for environment: $ENVIRONMENT"
echo "📍 Region: $AWS_REGION"
echo "🏢 Account: $AWS_ACCOUNT_ID"

# Step 1: Build and push Docker image to ECR
echo "🔨 Building Docker image..."
docker build -t $ECR_REPOSITORY:$IMAGE_TAG .

# Step 2: Tag image for ECR
echo "🏷️  Tagging image for ECR..."
docker tag $ECR_REPOSITORY:$IMAGE_TAG $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG

# Step 3: Login to ECR
echo "🔐 Logging into ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Step 4: Create ECR repository if it doesn't exist
echo "🏗️  Ensuring ECR repository exists..."
aws ecr describe-repositories --repository-names $ECR_REPOSITORY --region $AWS_REGION 2>/dev/null || \
aws ecr create-repository --repository-name $ECR_REPOSITORY --region $AWS_REGION

# Step 5: Push image to ECR
echo "📤 Pushing image to ECR..."
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG

# Step 6: Update task definition with new image
echo "📋 Updating task definition..."
sed "s/{AWS_ACCOUNT_ID}/$AWS_ACCOUNT_ID/g; s/{AWS_REGION}/$AWS_REGION/g" ecs-task-definition.json > task-definition-updated.json

# Step 7: Register new task definition
echo "📝 Registering new task definition..."
TASK_DEFINITION_ARN=$(aws ecs register-task-definition \
  --cli-input-json file://task-definition-updated.json \
  --region $AWS_REGION \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)

echo "✅ New task definition registered: $TASK_DEFINITION_ARN"

# Step 8: Update ECS service
echo "🔄 Updating ECS service..."
aws ecs update-service \
  --cluster $CLUSTER_NAME \
  --service $SERVICE_NAME \
  --task-definition $TASK_DEFINITION_ARN \
  --region $AWS_REGION

# Step 9: Wait for deployment to complete
echo "⏳ Waiting for service to become stable..."
aws ecs wait services-stable \
  --cluster $CLUSTER_NAME \
  --services $SERVICE_NAME \
  --region $AWS_REGION

# Step 10: Cleanup
echo "🧹 Cleaning up temporary files..."
rm -f task-definition-updated.json

echo "🎉 Deployment completed successfully!"
echo "📊 Service status:"
aws ecs describe-services \
  --cluster $CLUSTER_NAME \
  --services $SERVICE_NAME \
  --region $AWS_REGION \
  --query 'services[0].{Status:status,RunningCount:runningCount,DesiredCount:desiredCount}'

echo ""
echo "📝 To view logs:"
echo "aws logs tail /ecs/transcribe-service --follow --region $AWS_REGION"
