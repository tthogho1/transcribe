#!/bin/bash

# CodeBuild CI/CD Setup Script
# This script creates the necessary infrastructure for building and deploying the Transcribe service

set -e

# Configuration
PROJECT_NAME="transcribe-service"
ENVIRONMENT="production"
AWS_REGION="ap-northeast-1"
GITHUB_REPO="https://github.com/your-username/transcribe.git"
GITHUB_BRANCH="main"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Setting up CodeBuild CI/CD for Transcribe Service${NC}"
echo "Project: $PROJECT_NAME"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo

# Function to check if AWS CLI is configured
check_aws_cli() {
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}❌ AWS CLI is not installed${NC}"
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        echo -e "${RED}❌ AWS CLI is not configured or credentials are invalid${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ AWS CLI is configured${NC}"
}

# Function to deploy CloudFormation stack
deploy_stack() {
    local stack_name=$1
    local template_file=$2
    local parameters=$3
    
    echo -e "${YELLOW}📋 Deploying CloudFormation stack: $stack_name${NC}"
    
    aws cloudformation deploy \
        --template-file "$template_file" \
        --stack-name "$stack_name" \
        --parameter-overrides $parameters \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$AWS_REGION" \
        --no-fail-on-empty-changeset
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Stack $stack_name deployed successfully${NC}"
    else
        echo -e "${RED}❌ Failed to deploy stack $stack_name${NC}"
        exit 1
    fi
}

# Function to create ECR repository
create_ecr_repository() {
    local repo_name=$1
    
    echo -e "${YELLOW}🏗️ Creating ECR repository: $repo_name${NC}"
    
    if aws ecr describe-repositories --repository-names "$repo_name" --region "$AWS_REGION" &>/dev/null; then
        echo -e "${GREEN}✅ ECR repository $repo_name already exists${NC}"
    else
        aws ecr create-repository \
            --repository-name "$repo_name" \
            --region "$AWS_REGION" \
            --image-scanning-configuration scanOnPush=true
        
        # Set lifecycle policy
        aws ecr put-lifecycle-policy \
            --repository-name "$repo_name" \
            --lifecycle-policy-text '{
                "rules": [
                    {
                        "rulePriority": 1,
                        "selection": {
                            "tagStatus": "untagged",
                            "countType": "sinceImagePushed",
                            "countUnit": "days",
                            "countNumber": 7
                        },
                        "action": {
                            "type": "expire"
                        }
                    },
                    {
                        "rulePriority": 2,
                        "selection": {
                            "tagStatus": "tagged",
                            "tagPrefixList": ["build-"],
                            "countType": "imageCountMoreThan",
                            "countNumber": 20
                        },
                        "action": {
                            "type": "expire"
                        }
                    }
                ]
            }' \
            --region "$AWS_REGION"
        
        echo -e "${GREEN}✅ ECR repository $repo_name created${NC}"
    fi
}

# Function to trigger initial build
trigger_build() {
    local project_name=$1
    
    echo -e "${YELLOW}🔨 Triggering initial CodeBuild${NC}"
    
    BUILD_ID=$(aws codebuild start-build \
        --project-name "$project_name" \
        --query 'build.id' \
        --output text \
        --region "$AWS_REGION")
    
    echo -e "${GREEN}✅ Build started with ID: $BUILD_ID${NC}"
    echo "You can monitor the build at:"
    echo "https://console.aws.amazon.com/codesuite/codebuild/projects/$project_name/build/$BUILD_ID"
}

# Function to setup parameters in Parameter Store
setup_parameters() {
    echo -e "${YELLOW}⚙️ Setting up parameters in Systems Manager Parameter Store${NC}"
    
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    
    # Core parameters
    aws ssm put-parameter \
        --name "/codebuild/aws-account-id" \
        --value "$AWS_ACCOUNT_ID" \
        --type "String" \
        --overwrite \
        --region "$AWS_REGION" || true
    
    aws ssm put-parameter \
        --name "/codebuild/docker_buildkit" \
        --value "1" \
        --type "String" \
        --overwrite \
        --region "$AWS_REGION" || true
    
    # Transcribe service parameters (you'll need to update these)
    echo -e "${YELLOW}📝 Setting up placeholder parameters (update these with your actual values):${NC}"
    
    aws ssm put-parameter \
        --name "/transcribe/aws_access_key_id" \
        --value "PLACEHOLDER_UPDATE_ME" \
        --type "SecureString" \
        --overwrite \
        --region "$AWS_REGION" || true
    
    aws ssm put-parameter \
        --name "/transcribe/aws_secret_access_key" \
        --value "PLACEHOLDER_UPDATE_ME" \
        --type "SecureString" \
        --overwrite \
        --region "$AWS_REGION" || true
    
    aws ssm put-parameter \
        --name "/transcribe/sqs_queue_url" \
        --value "https://sqs.$AWS_REGION.amazonaws.com/$AWS_ACCOUNT_ID/audio-queue" \
        --type "String" \
        --overwrite \
        --region "$AWS_REGION" || true
    
    aws ssm put-parameter \
        --name "/transcribe/output_bucket" \
        --value "transcribe-output-bucket" \
        --type "String" \
        --overwrite \
        --region "$AWS_REGION" || true
    
    aws ssm put-parameter \
        --name "/transcribe/s3_bucket_name" \
        --value "transcribe-results-bucket" \
        --type "String" \
        --overwrite \
        --region "$AWS_REGION" || true
    
    aws ssm put-parameter \
        --name "/transcribe/zilliz_uri" \
        --value "PLACEHOLDER_UPDATE_ME" \
        --type "String" \
        --overwrite \
        --region "$AWS_REGION" || true
    
    aws ssm put-parameter \
        --name "/transcribe/zilliz_token" \
        --value "PLACEHOLDER_UPDATE_ME" \
        --type "SecureString" \
        --overwrite \
        --region "$AWS_REGION" || true
    
    echo -e "${GREEN}✅ Parameters set up (remember to update placeholder values)${NC}"
}

# Main execution
main() {
    echo -e "${GREEN}Starting setup process...${NC}"
    
    # Step 1: Check prerequisites
    check_aws_cli
    
    # Step 2: Setup parameters
    setup_parameters
    
    # Step 3: Create ECR repository
    create_ecr_repository "$PROJECT_NAME"
    
    # Step 4: Deploy CodeBuild infrastructure
    deploy_stack \
        "$PROJECT_NAME-codebuild" \
        "codebuild-infrastructure.yaml" \
        "ProjectName=$PROJECT_NAME Environment=$ENVIRONMENT GitHubRepo=$GITHUB_REPO GitHubBranch=$GITHUB_BRANCH"
    
    # Step 5: Display setup information
    echo
    echo -e "${GREEN}🎉 Setup completed successfully!${NC}"
    echo
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Update the placeholder parameters in Parameter Store:"
    echo "   - /transcribe/aws_access_key_id"
    echo "   - /transcribe/aws_secret_access_key"
    echo "   - /transcribe/zilliz_uri"
    echo "   - /transcribe/zilliz_token"
    echo
    echo "2. Update the GitHub repository URL in the CloudFormation template if needed"
    echo
    echo "3. Trigger a build manually or push to your repository"
    echo
    echo -e "${YELLOW}Useful commands:${NC}"
    echo "# Start a build manually:"
    echo "aws codebuild start-build --project-name $PROJECT_NAME --region $AWS_REGION"
    echo
    echo "# View build logs:"
    echo "aws logs tail /aws/codebuild/$PROJECT_NAME --follow --region $AWS_REGION"
    echo
    echo "# Update parameters:"
    echo "aws ssm put-parameter --name '/transcribe/parameter_name' --value 'new_value' --type 'SecureString' --overwrite --region $AWS_REGION"
    echo
    echo -e "${GREEN}✨ Your CI/CD pipeline is ready!${NC}"
}

# Run the main function
main "$@"
