# Infrastructure Migration Runbook

## Overview
This runbook guides the migration of shared infrastructure from the hokusai-data-pipeline repository to the centralized hokusai-infrastructure repository.

## Pre-Migration Checklist

- [ ] Backup current Terraform state
- [ ] Document all existing resource IDs
- [ ] Verify no pending changes in current infrastructure
- [ ] Coordinate migration window with all teams
- [ ] Ensure access to both repositories
- [ ] Verify AWS credentials and permissions

## Migration Steps

### Step 1: Backup Current State
```bash
# Create backup of current state
cd infrastructure/terraform
terraform state pull > terraform.tfstate.backup.$(date +%Y%m%d_%H%M%S)

# List all resources to be migrated
terraform state list | grep -E "(aws_lb\.|aws_lb_listener|aws_lb_target_group|aws_route53_record|aws_iam_role\.ecs)" > resources_to_migrate.txt
```

### Step 2: Prepare Infrastructure Repository
```bash
# In hokusai-infrastructure repository
mkdir -p terraform_module/data-pipeline
cp -r /path/to/hokusai-data-pipeline/terraform_module/data-pipeline/* terraform_module/data-pipeline/

# Add module to environment configuration
cat >> environments/development.tf <<EOF
module "data_pipeline" {
  source = "../terraform_module/data-pipeline"
  
  environment        = "development"
  project_name      = "hokusai"
  aws_region        = "us-east-1"
  vpc_id            = module.vpc.vpc_id
  public_subnet_ids = module.vpc.public_subnet_ids
  private_subnet_ids = module.vpc.private_subnet_ids
  certificate_arn   = var.certificate_arn
  route53_zone_id   = var.route53_zone_id
}
EOF
```

### Step 3: Import Resources to Central Infrastructure
```bash
# In hokusai-infrastructure repository
cd environments

# Import ALBs
terraform import module.data_pipeline.aws_lb.main arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:loadbalancer/app/hokusai-development/XXXXX
terraform import module.data_pipeline.aws_lb.auth arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:loadbalancer/app/hokusai-auth-development/XXXXX
terraform import module.data_pipeline.aws_lb.registry arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:loadbalancer/app/hokusai-registry-development/XXXXX

# Import Target Groups
terraform import module.data_pipeline.aws_lb_target_group.api arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:targetgroup/hokusai-api-development/XXXXX
terraform import module.data_pipeline.aws_lb_target_group.mlflow arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:targetgroup/hokusai-mlflow-development/XXXXX

# Import Route53 Records
terraform import module.data_pipeline.aws_route53_record.auth ZONE_ID_auth.hokus.ai_A
terraform import module.data_pipeline.aws_route53_record.registry ZONE_ID_registry.hokus.ai_A

# Import IAM Roles
terraform import module.data_pipeline.aws_iam_role.ecs_task_execution hokusai-ecs-execution-development
terraform import module.data_pipeline.aws_iam_role.ecs_task hokusai-ecs-task-development

# Verify imported state
terraform plan
```

### Step 4: Update Data Pipeline Repository
```bash
# In hokusai-data-pipeline repository
cd infrastructure/terraform

# Add remote state configuration
cp terraform_refactoring_example.tf data_sources.tf

# Comment out migrated resources
# Add to each migrated resource:
# /* MIGRATED TO CENTRAL INFRASTRUCTURE
# Original resource definition here...
# */

# Verify no resources will be destroyed
terraform plan
```

### Step 5: Remove Resources from Local State
```bash
# In hokusai-data-pipeline repository
# Remove each migrated resource from state
terraform state rm aws_lb.main
terraform state rm aws_lb.auth
terraform state rm aws_lb.registry
terraform state rm aws_lb_target_group.api
terraform state rm aws_lb_target_group.mlflow
terraform state rm aws_route53_record.auth
terraform state rm aws_route53_record.registry
terraform state rm aws_iam_role.ecs_task_execution
terraform state rm aws_iam_role.ecs_task

# Verify state
terraform state list
```

### Step 6: Apply Changes
```bash
# First in central infrastructure
cd /path/to/hokusai-infrastructure/environments
terraform apply

# Then in data pipeline
cd /path/to/hokusai-data-pipeline/infrastructure/terraform
terraform apply
```

## Validation Steps

1. **Verify ALB Functionality**
   ```bash
   # Test endpoints
   curl -I https://registry.hokus.ai/health
   curl -I https://auth.hokus.ai/health
   ```

2. **Check DNS Resolution**
   ```bash
   dig registry.hokus.ai
   dig auth.hokus.ai
   ```

3. **Verify ECS Services**
   ```bash
   aws ecs describe-services --cluster hokusai-development --services hokusai-api hokusai-mlflow
   ```

4. **Check Target Group Health**
   ```bash
   aws elbv2 describe-target-health --target-group-arn <ARN>
   ```

## Rollback Procedure

If issues occur during migration:

1. **Restore Original State**
   ```bash
   # In data pipeline repository
   terraform state push terraform.tfstate.backup.<timestamp>
   ```

2. **Remove Imported Resources**
   ```bash
   # In central infrastructure
   terraform state rm module.data_pipeline
   ```

3. **Reapply Original Configuration**
   ```bash
   terraform apply
   ```

## Post-Migration Tasks

- [ ] Update monitoring alerts to reference new resource IDs
- [ ] Update CI/CD pipelines with new state locations
- [ ] Document new resource ARNs
- [ ] Update team wikis and documentation
- [ ] Schedule follow-up review in 1 week

## Troubleshooting

### Common Issues

1. **Import Failures**
   - Verify resource ARN format
   - Check AWS permissions
   - Ensure resource exists

2. **State Lock Issues**
   - Release DynamoDB lock if needed
   - Check for concurrent operations

3. **Routing Issues**
   - Verify listener rule priorities
   - Check target group health
   - Review security group rules

## Emergency Contacts

- Infrastructure Team: #hokusai-infrastructure
- Data Pipeline Team: #hokusai-data-pipeline
- On-Call: pagerduty-infrastructure@hokusai.ai