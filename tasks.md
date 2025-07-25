# Infrastructure Consolidation - Implementation Tasks

## 1. Infrastructure Audit and Analysis
1. [x] Audit all Terraform files in infrastructure/terraform/
   a. [x] Review main.tf for shared resources
   b. [x] Review dedicated-albs.tf for ALB configurations
   c. [x] Review routing-fix.tf and alb-routing-fix.tf for routing rules
   d. [x] Review https-updates.tf for SSL configurations
   e. [x] Review variables.tf and outputs.tf

2. [x] Create comprehensive resource inventory
   a. [x] List all ALBs and their configurations
   b. [x] Document all listener rules and priorities
   c. [x] Map target groups to services
   d. [x] Identify Route53 DNS records
   e. [x] Catalog IAM roles and policies

3. [x] Analyze cross-service dependencies
   a. [x] Map service-to-service communications
   b. [x] Identify shared security groups
   c. [x] Document VPC and subnet usage
   d. [x] Review service discovery configurations

## 2. Module Structure Creation
4. [x] Create terraform_module directory structure
   a. [x] Create terraform_module/data-pipeline/ directory
   b. [x] Create standard terraform files (main.tf, variables.tf, outputs.tf)
   c. [x] Create specialized files (alb.tf, dns.tf, iam.tf)
   d. [x] Create README.md with usage examples
   e. [x] Add .gitignore for terraform files

## 3. ALB Module Extraction
5. [x] Extract main ALB configuration
   a. [x] Move aws_lb.main resource to alb.tf
   b. [x] Extract all associated listener rules
   c. [x] Move target group definitions
   d. [x] Convert environment-specific values to variables
   e. [x] Define outputs for ALB DNS and ARN

6. [x] Extract dedicated ALBs (auth and registry)
   a. [x] Move aws_lb.auth configuration
   b. [x] Move aws_lb.registry configuration
   c. [x] Extract HTTPS listeners and rules
   d. [x] Document routing priorities
   e. [x] Create variable for certificate ARN

## 4. DNS Module Extraction
7. [x] Extract Route53 configurations
   a. [x] Move auth.hokus.ai A record
   b. [x] Move registry.hokus.ai A record
   c. [x] Parameterize zone_id as variable
   d. [x] Add outputs for DNS names
   e. [x] Document TTL considerations

## 5. IAM Module Extraction
8. [x] Extract shared IAM roles
   a. [x] Move ECS task execution role
   b. [x] Move ECS task role
   c. [x] Extract S3 access policies
   d. [x] Parameterize role names
   e. [x] Output role ARNs

## 6. Resource Registry Documentation
9. [x] Create resource registry entry
   a. [x] Document all path prefixes owned
   b. [x] List DNS domains managed
   c. [x] Enumerate AWS resources
   d. [x] Add team contact information
   e. [x] Include SLA and support details

## 7. Local Terraform Refactoring (Dependent on Module Extraction)
10. [ ] Add remote state configuration
    a. [ ] Create data source for infrastructure state
    b. [ ] Configure S3 backend details
    c. [ ] Add required provider versions
    d. [ ] Document state bucket location
    e. [ ] Test state connectivity

11. [ ] Replace resource references with data lookups
    a. [ ] Update ALB references to use data sources
    b. [ ] Replace IAM role references
    c. [ ] Update security group references
    d. [ ] Modify target group attachments
    e. [ ] Update DNS record references

## 8. Testing and Validation
12. [ ] Create test environment
    a. [ ] Set up mock remote state
    b. [ ] Validate module syntax with terraform validate
    c. [ ] Run terraform plan to check changes
    d. [ ] Test module outputs
    e. [ ] Verify no resource recreation

13. [ ] Integration testing
    a. [ ] Test service connectivity
    b. [ ] Verify routing rules work
    c. [ ] Check DNS resolution
    d. [ ] Validate IAM permissions
    e. [ ] Test rollback procedures

## 9. Migration Preparation
14. [x] Create migration runbook
    a. [x] Document pre-migration checklist
    b. [x] Write state migration commands
    c. [x] Create backup procedures
    d. [x] Define rollback steps
    e. [x] Include validation tests

15. [ ] Prepare PR for hokusai-infrastructure
    a. [ ] Create PR template with module
    b. [ ] Include usage examples
    c. [ ] Add migration notes
    d. [ ] Request infrastructure team review
    e. [ ] Schedule migration window

## 10. Documentation
16. [ ] Update repository documentation
    a. [ ] Update README.md with new structure
    b. [ ] Document remote state usage
    c. [ ] Add troubleshooting guide
    d. [ ] Create architecture diagrams
    e. [ ] Update CI/CD documentation

## 11. Post-Migration Cleanup (Dependent on Successful Migration)
17. [ ] Remove migrated resources
    a. [ ] Delete moved ALB configurations
    b. [ ] Remove DNS records
    c. [ ] Clean up IAM roles
    d. [ ] Update .gitignore
    e. [ ] Archive old configurations

## Dependencies
- Tasks 7-8 depend on completing tasks 5-6
- Task 11 depends on completing task 10
- Task 17 depends on successful completion of all previous tasks and migration confirmation