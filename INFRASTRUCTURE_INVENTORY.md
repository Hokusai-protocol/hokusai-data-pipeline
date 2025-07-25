# Infrastructure Resource Inventory - Data Pipeline

## Shared Infrastructure Resources (To Move to hokusai-infrastructure)

### Application Load Balancers

1. **Main ALB** (`aws_lb.main`)
   - Name: `hokusai-${environment}`
   - Type: Application Load Balancer
   - Internal: false
   - DNS: Used by multiple services
   - Listeners: HTTP (80), HTTPS (443)

2. **Auth ALB** (`aws_lb.auth`) - from dedicated-albs.tf
   - Name: `hokusai-auth-${environment}`
   - Type: Application Load Balancer
   - Internal: false
   - Used for: auth.hokus.ai subdomain

3. **Registry ALB** (`aws_lb.registry`) - from dedicated-albs.tf
   - Name: `hokusai-registry-${environment}`
   - Type: Application Load Balancer
   - Internal: false
   - Used for: registry.hokus.ai subdomain

### ALB Listener Rules and Routing

#### Main ALB Rules:
- `aws_lb_listener_rule.api` (priority 100): `/api*` → API target group
- `aws_lb_listener_rule.registry_mlflow` (priority 40): `registry.hokus.ai` + `/mlflow/*`
- `aws_lb_listener_rule.registry_api` (priority 50): `registry.hokus.ai` catch-all
- `aws_lb_listener_rule.mlflow` (priority 200): `/mlflow/*` → MLflow target group

#### Routing Fix Rules:
- `aws_lb_listener_rule.auth_service_api` (priority 80): `auth.hokus.ai` + `/api/*`
- `aws_lb_listener_rule.api_v1` (priority 95): `/api/v1/*`, `/api/health/*`
- `aws_lb_listener_rule.api_mlflow_proxy` (priority 85): `/api/mlflow/*`

#### Dedicated ALB Rules:
- Auth ALB: `/api/v1/*`, `/health`
- Registry ALB: `/mlflow/*`, `/api/mlflow/*`, `/api/*`

### Target Groups (Shared)

1. **API Target Group** (`aws_lb_target_group.api`)
   - Name: `hokusai-api-${environment}`
   - Port: 8001
   - Used by: Multiple services

2. **MLflow Target Group** (`aws_lb_target_group.mlflow`)
   - Name: `hokusai-mlflow-${environment}`
   - Port: 5000

3. **Auth Target Group** (`aws_lb_target_group.auth`)
   - Name: `hokusai-auth-ded-${environment}`
   - Port: 8000

4. **Registry API Target Group** (`aws_lb_target_group.registry_api`)
   - Name: `hokusai-api-ded-${environment}`
   - Port: 8001

5. **Registry MLflow Target Group** (`aws_lb_target_group.registry_mlflow`)
   - Name: `hokusai-mlflow-ded-${environment}`
   - Port: 5000

### Route53 DNS Records

1. **auth.hokus.ai** (`aws_route53_record.auth`)
   - Type: A record (ALIAS)
   - Points to: Auth ALB

2. **registry.hokus.ai** (`aws_route53_record.registry`)
   - Type: A record (ALIAS)
   - Points to: Registry ALB

### Shared IAM Roles

1. **ECS Task Execution Role** (`aws_iam_role.ecs_task_execution`)
   - Name: `hokusai-ecs-execution-${environment}`
   - Used by: All ECS services
   - Policy: AmazonECSTaskExecutionRolePolicy

2. **ECS Task Role** (`aws_iam_role.ecs_task`)
   - Name: `hokusai-ecs-task-${environment}`
   - Used by: All ECS services
   - Includes S3 access policies

### VPC and Networking (Potentially Shared)

1. **VPC Module** (`module.vpc`)
   - Name: `hokusai-${environment}-vpc`
   - CIDR: Configured via variables
   - Includes public/private subnets
   - NAT Gateway configuration

### Security Groups (Some Shared)

1. **ALB Security Group** (`aws_security_group.alb`)
   - Name: `hokusai-alb-*`
   - Allows HTTP/HTTPS ingress
   - Used by all ALBs

## Service-Specific Resources (Stay in data-pipeline)

### Data Storage
- RDS PostgreSQL instance (`aws_db_instance.mlflow`)
- S3 buckets: mlflow_artifacts, pipeline_data
- Secrets Manager secrets

### ECS Resources
- ECS Cluster (`aws_ecs_cluster.main`)
- Task Definitions (api, mlflow)
- ECS Services (api, mlflow)
- ECR Repositories

### Service-Specific Security Groups
- `aws_security_group.ecs_tasks`
- `aws_security_group.rds`

### Monitoring
- CloudWatch Log Groups
- CloudWatch Alarms
- SNS Topics

## Path Ownership Summary

### Data Pipeline Service Owns:
- `/api/v1/*` - API v1 endpoints
- `/api/mlflow/*` - MLflow proxy endpoints
- `/mlflow/*` - Direct MLflow access
- `/api/health/*` - Health check endpoints

### DNS Ownership:
- `registry.hokus.ai` - Shared with auth service
- Internal MLflow endpoints

## Migration Considerations

1. **ALB Consolidation**: Multiple ALBs serving similar purposes could be consolidated
2. **Routing Complexity**: Current routing has overlapping rules that need careful migration
3. **Cross-Service Dependencies**: Auth service uses same ALB infrastructure
4. **Certificate Management**: HTTPS certificates need to be managed centrally