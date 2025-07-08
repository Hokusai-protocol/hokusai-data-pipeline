#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &>/dev/null; then
    print_error "AWS CLI is not configured. Please run 'aws configure' first."
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-us-east-1}

print_info "Setting up GitHub Actions OIDC for AWS account $ACCOUNT_ID in region $REGION"

# Create OIDC provider
print_info "Creating OIDC provider..."
if aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 1c58a3a8518e8759bf075b76b750d4f2df264fcd \
  2>/dev/null; then
    print_info "OIDC provider created successfully"
else
    print_warn "OIDC provider already exists or creation failed"
fi

# Create trust policy
print_info "Creating trust policy..."
cat > /tmp/github-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:Hokusai-protocol/hokusai-data-pipeline:*"
        }
      }
    }
  ]
}
EOF

# Create deployment policy
print_info "Creating deployment policy..."
cat > /tmp/github-deploy-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRAccess",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:BatchGetImage",
        "ecr:DescribeRepositories",
        "ecr:CreateRepository"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECSAccess",
      "Effect": "Allow",
      "Action": [
        "ecs:UpdateService",
        "ecs:DescribeServices",
        "ecs:DescribeTaskDefinition",
        "ecs:RegisterTaskDefinition",
        "ecs:ListTasks",
        "ecs:DescribeTasks",
        "ecs:DescribeClusters"
      ],
      "Resource": "*"
    },
    {
      "Sid": "PassRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::${ACCOUNT_ID}:role/*"
    },
    {
      "Sid": "TerraformState",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:GetBucketLocation",
        "s3:GetBucketVersioning"
      ],
      "Resource": [
        "arn:aws:s3:::hokusai-terraform-state-*",
        "arn:aws:s3:::hokusai-terraform-state-*/*"
      ]
    },
    {
      "Sid": "TerraformLock",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem"
      ],
      "Resource": "arn:aws:dynamodb:*:${ACCOUNT_ID}:table/terraform-state-lock-*"
    },
    {
      "Sid": "TerraformProvision",
      "Effect": "Allow",
      "Action": [
        "ec2:*",
        "rds:*",
        "elasticloadbalancing:*",
        "logs:*",
        "secretsmanager:*",
        "ssm:*",
        "iam:*",
        "vpc:*",
        "autoscaling:*",
        "cloudwatch:*",
        "sns:*",
        "route53:*",
        "acm:*"
      ],
      "Resource": "*"
    }
  ]
}
EOF

# Create or update the policy
print_info "Creating/updating IAM policy..."
if aws iam create-policy \
  --policy-name GitHubActionsDeployPolicy \
  --policy-document file:///tmp/github-deploy-policy.json \
  --description "Policy for GitHub Actions to deploy Hokusai infrastructure" \
  2>/dev/null; then
    print_info "Policy created successfully"
    POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/GitHubActionsDeployPolicy"
else
    print_warn "Policy already exists, updating..."
    # Get current policy version
    POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/GitHubActionsDeployPolicy"
    VERSIONS=$(aws iam list-policy-versions --policy-arn $POLICY_ARN --query 'Versions[?!IsDefaultVersion].VersionId' --output text)
    
    # Delete old versions if there are 5 (max allowed)
    VERSION_COUNT=$(echo $VERSIONS | wc -w)
    if [ $VERSION_COUNT -ge 4 ]; then
        OLDEST_VERSION=$(echo $VERSIONS | awk '{print $1}')
        aws iam delete-policy-version --policy-arn $POLICY_ARN --version-id $OLDEST_VERSION
    fi
    
    # Create new version
    aws iam create-policy-version \
      --policy-arn $POLICY_ARN \
      --policy-document file:///tmp/github-deploy-policy.json \
      --set-as-default
fi

# Create the role
print_info "Creating IAM role..."
if aws iam create-role \
  --role-name GitHubActionsDeployRole \
  --assume-role-policy-document file:///tmp/github-trust-policy.json \
  --description "Role for GitHub Actions to deploy Hokusai infrastructure" \
  2>/dev/null; then
    print_info "Role created successfully"
else
    print_warn "Role already exists, updating trust policy..."
    aws iam update-assume-role-policy \
      --role-name GitHubActionsDeployRole \
      --policy-document file:///tmp/github-trust-policy.json
fi

# Attach the policy to the role
print_info "Attaching policy to role..."
aws iam attach-role-policy \
  --role-name GitHubActionsDeployRole \
  --policy-arn $POLICY_ARN

# Get and display the role ARN
ROLE_ARN=$(aws iam get-role --role-name GitHubActionsDeployRole --query 'Role.Arn' --output text)

# Clean up temp files
rm -f /tmp/github-trust-policy.json /tmp/github-deploy-policy.json

print_info "✅ Setup complete!"
echo ""
echo "=========================================="
echo "Add this to your GitHub repository secrets:"
echo "=========================================="
echo ""
echo "  Name:  AWS_DEPLOY_ROLE_ARN"
echo "  Value: ${GREEN}${ROLE_ARN}${NC}"
echo ""
echo "To add this secret:"
echo "1. Go to https://github.com/Hokusai-protocol/hokusai-data-pipeline/settings/secrets/actions"
echo "2. Click 'New repository secret'"
echo "3. Enter the name and value above"
echo "4. Click 'Add secret'"
echo ""
echo "The role has permissions to:"
echo "  - Push/pull from ECR"
echo "  - Update ECS services"
echo "  - Manage Terraform state in S3"
echo "  - Create AWS infrastructure via Terraform"