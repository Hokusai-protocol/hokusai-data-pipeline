#!/bin/bash

# Migration Script to Centralized Infrastructure
# This script updates the existing configuration to use centralized resources

set -e

echo "=== Migrating to Centralized Infrastructure ==="
echo

# Check if we're in the right directory
if [ ! -f "main.tf" ]; then
    echo "Error: Please run this script from the infrastructure/terraform directory"
    exit 1
fi

# Step 1: Backup current configuration
echo "Step 1: Creating backup of current configuration..."
mkdir -p backups/$(date +%Y%m%d_%H%M%S)
cp *.tf backups/$(date +%Y%m%d_%H%M%S)/

# Step 2: Update the API service to use centralized target group
echo "Step 2: Updating API service configuration..."
cat > api-service-central.tf << 'EOF'
# Updated API service to use centralized infrastructure target group
resource "aws_ecs_service" "api_central" {
  name            = "${var.project_name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api_updated.arn
  desired_count   = var.api_desired_count
  
  launch_type = "FARGATE"
  
  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }
  
  load_balancer {
    # Use centralized target group ARN
    target_group_arn = "arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81"
    container_name   = "${var.project_name}-api"
    container_port   = 8001
  }
  
  depends_on = [
    aws_service_discovery_service.mlflow
  ]

  lifecycle {
    create_before_destroy = true
  }
}
EOF

# Step 3: Update the MLflow service to use centralized target group
echo "Step 3: Updating MLflow service configuration..."
cat > mlflow-service-central.tf << 'EOF'
# Updated MLflow service to use centralized infrastructure target group
resource "aws_ecs_service" "mlflow_central" {
  name            = "${var.project_name}-mlflow"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.mlflow.arn
  desired_count   = var.mlflow_desired_count
  
  launch_type = "FARGATE"
  
  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }
  
  load_balancer {
    # Use centralized target group ARN
    target_group_arn = "arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-tg-development/9518cac0d6af96bb"
    container_name   = "${var.project_name}-mlflow"
    container_port   = 5000
  }
  
  depends_on = [
    aws_service_discovery_service.mlflow
  ]

  lifecycle {
    create_before_destroy = true
  }
}
EOF

# Step 4: Remove old services from state (they'll be replaced)
echo "Step 4: Preparing to replace services..."
echo "WARNING: This will remove the old services and create new ones pointing to centralized target groups"
echo "Do you want to continue? (yes/no)"
read -r response

if [ "$response" != "yes" ]; then
    echo "Migration cancelled."
    exit 0
fi

# Step 5: Apply the changes
echo "Step 5: Applying configuration changes..."
terraform init
terraform plan -out=migration.tfplan

echo
echo "Please review the plan above. This should show:"
echo "- Removal of old ECS services"
echo "- Creation of new ECS services with centralized target groups"
echo
echo "Do you want to apply these changes? (yes/no)"
read -r response

if [ "$response" != "yes" ]; then
    echo "Migration cancelled."
    exit 0
fi

terraform apply migration.tfplan

echo
echo "=== Migration Complete ==="
echo
echo "Next steps:"
echo "1. Verify services are running:"
echo "   aws ecs describe-services --cluster hokusai-development --services hokusai-api hokusai-mlflow"
echo
echo "2. Check target group health:"
echo "   aws elbv2 describe-target-health --target-group-arn arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81"
echo "   aws elbv2 describe-target-health --target-group-arn arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-tg-development/9518cac0d6af96bb"
echo
echo "3. Contact infrastructure team to enable listener rules"
echo
echo "4. Test endpoints once listener rules are enabled:
echo "   - API: https://hokusai-dp-development-465790699.us-east-1.elb.amazonaws.com/api/health"
echo "   - MLflow: https://hokusai-dp-development-465790699.us-east-1.elb.amazonaws.com/mlflow"