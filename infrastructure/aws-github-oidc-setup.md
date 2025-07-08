# Setting up AWS IAM Role for GitHub Actions (OIDC)

This guide explains how to create an IAM role that GitHub Actions can assume using OpenID Connect (OIDC).

## Prerequisites

- AWS CLI configured with administrative permissions
- Your AWS account ID (find it with `aws sts get-caller-identity`)
- Your GitHub repository details

## Step 1: Create the OIDC Identity Provider

First, add GitHub as an OIDC provider to your AWS account:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 1c58a3a8518e8759bf075b76b750d4f2df264fcd
```

Note: If you get an error that the provider already exists, that's fine - it means it's already set up.

## Step 2: Create the Trust Policy

Create a file named `github-actions-trust-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
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
```

Replace `YOUR_ACCOUNT_ID` with your actual AWS account ID.

## Step 3: Create the IAM Policy

Create a file named `github-actions-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:BatchGetImage"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecs:UpdateService",
        "ecs:DescribeServices",
        "ecs:DescribeTaskDefinition",
        "ecs:RegisterTaskDefinition",
        "ecs:ListTasks",
        "ecs:DescribeTasks"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "iam:PassRole"
      ],
      "Resource": "arn:aws:iam::*:role/ecsTaskExecutionRole"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::hokusai-terraform-state-*",
        "arn:aws:s3:::hokusai-terraform-state-*/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/terraform-state-lock-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:*",
        "rds:*",
        "elasticloadbalancing:*",
        "logs:*",
        "secretsmanager:*",
        "ssm:*"
      ],
      "Resource": "*"
    }
  ]
}
```

## Step 4: Create the IAM Role

Run these commands to create the role:

```bash
# Get your account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Update the trust policy with your account ID
sed -i "s/YOUR_ACCOUNT_ID/$ACCOUNT_ID/g" github-actions-trust-policy.json

# Create the IAM policy
aws iam create-policy \
  --policy-name GitHubActionsDeployPolicy \
  --policy-document file://github-actions-policy.json \
  --description "Policy for GitHub Actions to deploy Hokusai infrastructure"

# Create the IAM role
aws iam create-role \
  --role-name GitHubActionsDeployRole \
  --assume-role-policy-document file://github-actions-trust-policy.json \
  --description "Role for GitHub Actions to deploy Hokusai infrastructure"

# Attach the policy to the role
aws iam attach-role-policy \
  --role-name GitHubActionsDeployRole \
  --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/GitHubActionsDeployPolicy

# Get the role ARN
aws iam get-role --role-name GitHubActionsDeployRole --query 'Role.Arn' --output text
```

## Step 5: Add the Role ARN to GitHub Secrets

1. Copy the role ARN from the last command (it will look like `arn:aws:iam::123456789012:role/GitHubActionsDeployRole`)
2. Go to your GitHub repository
3. Navigate to Settings → Secrets and variables → Actions
4. Click "New repository secret"
5. Name: `AWS_DEPLOY_ROLE_ARN`
6. Value: Paste the role ARN
7. Click "Add secret"

## One-Line Setup Script

For convenience, here's a script that does everything:

```bash
#!/bin/bash
set -e

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-us-east-1}

echo "Setting up GitHub Actions OIDC for AWS account $ACCOUNT_ID"

# Create OIDC provider
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 1c58a3a8518e8759bf075b76b750d4f2df264fcd \
  2>/dev/null || echo "OIDC provider already exists"

# Create trust policy
cat > /tmp/trust-policy.json <<EOF
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

# Create the role
aws iam create-role \
  --role-name GitHubActionsDeployRole \
  --assume-role-policy-document file:///tmp/trust-policy.json \
  --description "Role for GitHub Actions to deploy Hokusai infrastructure" \
  2>/dev/null || echo "Role already exists"

# Attach necessary policies
aws iam attach-role-policy \
  --role-name GitHubActionsDeployRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser

aws iam attach-role-policy \
  --role-name GitHubActionsDeployRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonECS_FullAccess

# For Terraform (you might want to restrict this more)
aws iam attach-role-policy \
  --role-name GitHubActionsDeployRole \
  --policy-arn arn:aws:iam::aws:policy/PowerUserAccess

# Get and display the role ARN
ROLE_ARN=$(aws iam get-role --role-name GitHubActionsDeployRole --query 'Role.Arn' --output text)
echo ""
echo "✅ Setup complete!"
echo ""
echo "Add this to your GitHub repository secrets:"
echo "  Name: AWS_DEPLOY_ROLE_ARN"
echo "  Value: $ROLE_ARN"
```

Save this as `setup-github-oidc.sh` and run:
```bash
chmod +x setup-github-oidc.sh
./setup-github-oidc.sh
```

## Troubleshooting

### "Could not assume role" error
- Verify the repository name in the trust policy matches exactly
- Check that the OIDC provider thumbprints are correct
- Ensure the role ARN in GitHub secrets is correct

### "Access denied" errors
- The role might need additional permissions
- Check CloudTrail logs to see what specific permissions are missing
- Add them to the policy and update with:
  ```bash
  aws iam put-role-policy --role-name GitHubActionsDeployRole --policy-name DeployPolicy --policy-document file://updated-policy.json
  ```

### Testing the setup
You can test if the role works by adding this step to your workflow:
```yaml
- name: Test AWS credentials
  run: |
    aws sts get-caller-identity
    aws ecr describe-repositories
```