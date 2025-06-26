# Infrastructure Setup PRD

## Objectives

Establish cloud-based infrastructure to make the Hokusai data pipeline available to external projects with secure model storage, MLFlow tracking, authentication, and automated deployment.

## Personas

- **External Developer**: Integrates Hokusai ML platform into their project, needs API access and model storage
- **Data Contributor**: Submits data to improve models, requires secure authentication
- **Platform Administrator**: Manages infrastructure, monitors usage, and handles deployments

## Success Criteria

1. External projects can access Hokusai ML platform APIs with authentication
2. Models and artifacts are securely stored in S3-compatible storage
3. MLFlow tracking server is accessible for experiment tracking
4. Automated CI/CD deploys updates to production when merged to main
5. Infrastructure supports high availability and scalability

## Tasks

### 1. AWS Infrastructure Setup

Set up core AWS services for the Hokusai platform:

- **S3 Buckets**:
  - `hokusai-mlflow-artifacts`: Store model artifacts and datasets
  - `hokusai-pipeline-data`: Store contributed data and outputs
  - Configure lifecycle policies for cost optimization
  - Enable versioning and encryption

- **RDS PostgreSQL**:
  - Database for MLFlow backend store
  - Multi-AZ deployment for high availability
  - Automated backups with 7-day retention

- **EC2/ECS**:
  - Container hosting for API and MLFlow server
  - Auto-scaling configuration
  - Load balancer setup

### 2. Authentication System

Implement authentication for external access:

- **API Key Management**:
  - Generate and manage API keys for external projects
  - Store keys securely in AWS Secrets Manager
  - Implement key rotation policies

- **ETH Address Authentication**:
  - Support ETH wallet address as authentication method
  - Implement signature verification for requests
  - Map ETH addresses to API permissions

### 3. MLFlow Server Deployment

Deploy MLFlow tracking server on AWS:

- Configure MLFlow with S3 backend for artifacts
- Set up PostgreSQL as backend store
- Enable authentication for MLFlow UI
- Configure HTTPS with SSL certificates

### 4. API Service Deployment

Deploy the Hokusai Model Registry API:

- Containerize API service using existing Dockerfile
- Deploy to ECS with auto-scaling
- Configure Application Load Balancer
- Set up health checks and monitoring

### 5. CI/CD Pipeline

Implement automated deployment pipeline:

- **GitHub Actions Workflow**:
  - Trigger on merge to main branch
  - Run tests and build containers
  - Deploy to AWS ECS
  - Update infrastructure as code

- **Infrastructure as Code**:
  - Use Terraform or CloudFormation
  - Version control infrastructure changes
  - Implement staging environment

### 6. Monitoring and Logging

Set up observability infrastructure:

- CloudWatch logs for all services
- Prometheus/Grafana for metrics (optional)
- Alert configuration for critical issues
- Cost monitoring and optimization

### 7. Documentation

Create comprehensive deployment documentation:

- Infrastructure architecture diagram
- Deployment procedures
- Authentication setup guide
- Troubleshooting runbook
- API endpoint documentation

### 8. Security Hardening

Implement security best practices:

- VPC configuration with private subnets
- Security groups with minimal permissions
- IAM roles and policies
- Secrets management
- Regular security audits