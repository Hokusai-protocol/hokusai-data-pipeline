# Infrastructure Consolidation - Product Requirements Document

## Objectives

Extract and prepare all shared infrastructure resources from the hokusai-data-pipeline repository for migration to a centralized hokusai-infrastructure repository. This consolidation will eliminate routing conflicts, reduce operational drift, and establish standardized infrastructure management.

## Personas

- **Infrastructure Team**: Will manage the centralized hokusai-infrastructure repository and approve provisioning requests
- **Data Pipeline Team**: Currently owns infrastructure in this repository that needs to be migrated
- **DevOps Engineers**: Will execute the extraction and migration process
- **Platform Teams**: Other Hokusai services that will benefit from centralized infrastructure

## Success Criteria

1. All shared infrastructure resources identified and documented
2. Terraform modules created for data-pipeline infrastructure
3. Resource registry entries prepared with clear ownership
4. Local terraform refactored to use remote state references
5. Zero disruption to existing services during preparation
6. Complete migration plan with rollback procedures

## Tasks

### Phase 1: Infrastructure Audit
- Identify all ALB resources, listeners, and routing rules
- Document Route53 DNS records (registry.hokus.ai, auth.hokus.ai)
- Catalog shared IAM roles and policies
- Review VPC and networking components for shared usage
- Identify cross-service dependencies and integrations

### Phase 2: Module Extraction
- Create terraform_module/data-pipeline/ directory structure
- Extract ALB configuration (main and dedicated ALBs)
- Extract Route53 DNS records for *.hokus.ai domains
- Extract shared IAM roles (ECS execution, task roles)
- Convert hardcoded values to variables

### Phase 3: Resource Documentation
- Create resource registry entry for data-pipeline service
- Document path ownership (/api/*, /mlflow/*, /auth/*)
- List all provisioned AWS resources
- Define service contact information
- Document integration points with other services

### Phase 4: Local Refactoring
- Add remote state data source configuration
- Replace local resource references with data lookups
- Update service configurations for remote outputs
- Test connectivity with mock remote state
- Document all required outputs from central infrastructure

### Phase 5: Migration Preparation
- Create detailed migration runbook
- Define terraform state migration commands
- Prepare PR template for hokusai-infrastructure
- Create rollback procedures
- Define success validation criteria

## Shared Infrastructure Components

Based on terraform audit, these resources should move to hokusai-infrastructure:

### Load Balancers and Routing
- Main ALB (hokusai-development)
- Auth ALB (hokusai-auth-development)
- Registry ALB (hokusai-registry-development)
- All ALB listeners and routing rules
- Target groups for cross-service routing

### DNS and Domains
- Route53 A records for auth.hokus.ai
- Route53 A records for registry.hokus.ai
- Any other *.hokus.ai subdomain records

### Cross-Service IAM Roles
- Shared ECS task execution roles
- Cross-service assume roles
- S3 bucket policies for shared access

### Networking (if shared)
- VPC configuration (if used by multiple services)
- Public/private subnets
- NAT gateways
- Internet gateways

## Service-Specific Components (Stay Local)

These resources remain in the data-pipeline repository:

- ECS cluster and services
- Service-specific task definitions
- RDS instances (MLflow database)
- S3 buckets (mlflow-artifacts, pipeline-data)
- Service-specific security groups
- CloudWatch log groups and alarms
- ECR repositories
- Secrets Manager entries

## Technical Requirements

### Module Structure
```
terraform_module/data-pipeline/
├── main.tf           # Core infrastructure resources
├── alb.tf           # Load balancer configurations
├── dns.tf           # Route53 records
├── iam.tf           # Shared IAM roles
├── variables.tf     # Input variables
├── outputs.tf       # Exported values
└── README.md        # Usage documentation
```

### Required Outputs
- ALB ARNs and DNS names
- Target group ARNs
- IAM role ARNs
- Route53 zone IDs
- Security group IDs

### Variable Requirements
- Environment (development/staging/production)
- Project name
- AWS region
- Certificate ARN
- Route53 zone ID

## Resource Registry Entry

```markdown
### Service: data-pipeline

**Path Prefixes**: 
- `/api/*` - Main API endpoints
- `/api/mlflow/*` - MLflow proxy endpoints
- `/mlflow/*` - Direct MLflow access

**DNS**: 
- `registry.hokus.ai` - Model registry and API
- Internal MLflow endpoint

**Provisioned Resources**:
- ALB: hokusai-development (shared main ALB)
- ALB: hokusai-registry-development (dedicated registry ALB)
- Target Groups: api, mlflow, registry_api, registry_mlflow
- Route53 A record: registry.hokus.ai
- IAM Roles: ecs-execution-role, ecs-task-role

**Owner**: `data-pipeline-team@hokusai.ai`  
**Contact**: `slack: #hokusai-data-pipeline`
```

## Migration Timeline

### Week 1: Preparation
- Complete infrastructure audit
- Extract terraform modules
- Create documentation

### Week 2: Module Submission
- Submit PR to hokusai-infrastructure
- Add registry entry
- Review with infrastructure team

### Week 3-4: Testing and Migration
- Test with remote state references
- Execute state migration
- Validate all services functional

### Week 5: Finalization
- Remove migrated resources from local repo
- Update all documentation
- Monitor for issues

## Risk Mitigation

1. **Service Disruption**: Test all changes in staging first
2. **State Corruption**: Backup terraform state before migration
3. **Missing Dependencies**: Comprehensive dependency mapping
4. **DNS Propagation**: Plan for DNS TTL during migration
5. **Rollback Complexity**: Keep original resources until migration validated