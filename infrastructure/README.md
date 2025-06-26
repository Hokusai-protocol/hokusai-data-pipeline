# Hokusai Infrastructure

This directory contains the infrastructure as code (IaC) configuration for deploying the Hokusai data pipeline platform to AWS.

## Architecture Overview

The infrastructure includes:

- **VPC**: Multi-AZ VPC with public and private subnets
- **ECS Fargate**: Container orchestration for API and MLflow services
- **RDS PostgreSQL**: Managed database for MLflow backend store
- **S3**: Object storage for MLflow artifacts and pipeline data
- **Application Load Balancer**: HTTPS load balancing for services
- **CloudWatch**: Monitoring, logging, and alerting
- **Secrets Manager**: Secure storage for API keys and secrets
- **ECR**: Container registry for Docker images

## Prerequisites

1. **AWS CLI**: Install and configure AWS CLI with appropriate credentials
   ```bash
   aws configure
   ```

2. **Terraform**: Install Terraform 1.0 or later
   ```bash
   brew install terraform  # macOS
   ```

3. **Docker**: Required for building container images

4. **Environment Variables**: Set required environment variables
   ```bash
   export AWS_REGION=us-east-1
   export ENVIRONMENT=development
   export DATABASE_PASSWORD=<secure-password>
   export API_SECRET_KEY=<secure-key>
   ```

## Directory Structure

```
infrastructure/
├── terraform/          # Terraform configuration files
│   ├── main.tf        # Main infrastructure resources
│   ├── variables.tf   # Input variables
│   ├── outputs.tf     # Output values
│   └── terraform.tfvars.example  # Example variables file
└── scripts/           # Deployment and maintenance scripts
    ├── deploy.sh      # Main deployment script
    ├── validate.sh    # Infrastructure validation
    └── destroy.sh     # Teardown script
```

## Deployment Guide

### 1. Initial Setup

1. Clone the repository and navigate to the infrastructure directory:
   ```bash
   cd infrastructure
   ```

2. Copy the example variables file and update values:
   ```bash
   cp terraform/terraform.tfvars.example terraform/terraform.tfvars
   # Edit terraform.tfvars with your values
   ```

3. Create S3 bucket for Terraform state (one-time setup):
   ```bash
   aws s3 mb s3://hokusai-terraform-state-${ENVIRONMENT}
   ```

### 2. Deploy Infrastructure

Run the deployment script:
```bash
./scripts/deploy.sh
```

This script will:
1. Initialize Terraform
2. Validate configuration
3. Plan infrastructure changes
4. Apply changes (with confirmation)
5. Build and push Docker images
6. Deploy ECS services

### 3. Validate Deployment

After deployment, validate all services are running:
```bash
./scripts/validate.sh
```

This will check:
- API health endpoints
- MLflow UI accessibility
- S3 bucket access
- RDS database status
- ECS service health

### 4. Access Services

After successful deployment:

- **API Endpoint**: Output from `terraform output api_endpoint`
- **MLflow UI**: Output from `terraform output mlflow_endpoint`
- **S3 Buckets**: 
  - Artifacts: `hokusai-mlflow-artifacts-<environment>`
  - Pipeline: `hokusai-pipeline-data-<environment>`

## Authentication

The platform supports two authentication methods:

### API Key Authentication

1. Generate API key using the API endpoint
2. Include in requests: `Authorization: Bearer <api-key>`

### Ethereum Address Authentication

1. Sign a message with your ETH private key
2. Include headers:
   - `X-ETH-Address: <your-address>`
   - `X-ETH-Signature: <signature>`
   - `X-ETH-Message: <original-message>`

## Monitoring

### CloudWatch Dashboards

Access CloudWatch dashboards in AWS Console to monitor:
- API request rates and latencies
- ECS task health and resource usage
- RDS database performance
- S3 bucket metrics

### Alerts

CloudWatch alarms are configured for:
- API unhealthy hosts
- RDS high CPU utilization
- ECS task failures

Alerts are sent to the SNS topic configured in Terraform.

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/deploy.yml`) automates:

1. **On Pull Request**: Run tests and validation
2. **On Merge to Main**: 
   - Build and push Docker images
   - Update infrastructure with Terraform
   - Deploy new ECS task definitions
   - Validate deployment

### Required GitHub Secrets

Configure these secrets in your GitHub repository:
- `AWS_DEPLOY_ROLE_ARN`: IAM role for deployments
- `TERRAFORM_STATE_BUCKET`: S3 bucket for Terraform state
- `DATABASE_PASSWORD`: RDS database password
- `API_SECRET_KEY`: API authentication secret

## Security Considerations

1. **Network Security**:
   - Services run in private subnets
   - Security groups restrict access
   - ALB handles SSL termination

2. **Secrets Management**:
   - Sensitive values stored in AWS Secrets Manager
   - IAM roles for service authentication
   - Encrypted S3 buckets

3. **Access Control**:
   - API authentication required
   - S3 bucket policies restrict access
   - RDS accessible only from ECS tasks

## Maintenance

### Update Infrastructure

To update infrastructure configuration:
1. Modify Terraform files
2. Run `./scripts/deploy.sh`
3. Review and approve changes

### Scale Services

Update service counts in `terraform.tfvars`:
```hcl
api_desired_count = 3
mlflow_desired_count = 2
```

### Destroy Infrastructure

To tear down all resources:
```bash
./scripts/destroy.sh
```

**Warning**: This will delete all data and resources!

## Troubleshooting

### Common Issues

1. **Terraform State Lock**: If Terraform state is locked:
   ```bash
   terraform force-unlock <lock-id>
   ```

2. **ECS Service Not Starting**: Check CloudWatch logs:
   ```bash
   aws logs tail /ecs/hokusai/api/production --follow
   ```

3. **Database Connection Failed**: Verify security groups and RDS status

### Debug Commands

```bash
# Check ECS service status
aws ecs describe-services --cluster hokusai-production --services hokusai-api

# View recent CloudWatch logs
aws logs filter-log-events --log-group-name /ecs/hokusai/api/production --start-time $(date -u -d '5 minutes ago' +%s)000

# Test S3 access
aws s3 ls s3://hokusai-mlflow-artifacts-production/
```

## Cost Optimization

To reduce costs in non-production environments:

1. Use smaller instance types:
   ```hcl
   db_instance_class = "db.t3.micro"
   ```

2. Reduce service counts:
   ```hcl
   api_desired_count = 1
   mlflow_desired_count = 1
   ```

3. Use single NAT gateway:
   ```hcl
   single_nat_gateway = true  # Set in main.tf for non-production
   ```

4. Enable S3 lifecycle policies for old artifacts

## Support

For issues or questions:
1. Check CloudWatch logs for error details
2. Review Terraform output for resource information
3. Consult AWS documentation for service-specific issues
4. Open an issue in the repository for platform-specific problems