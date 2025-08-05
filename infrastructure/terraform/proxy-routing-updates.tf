# Proxy Routing Updates - Minimal changes to enable internal MLflow routing

# Update only the environment variables we need in the API service
# This approach uses data sources to reference existing resources

# Data source to get the current API task definition
data "aws_ecs_task_definition" "api_current" {
  task_definition = "${var.project_name}-api-${var.environment}"
}

# Local variable to store the MLflow internal URL
locals {
  mlflow_internal_url = "http://${var.project_name}-mlflow.${var.project_name}-${var.environment}.local:5000"
}

# Output the MLflow URL for reference
output "mlflow_internal_url_config" {
  value = local.mlflow_internal_url
  description = "Internal MLflow URL to be configured in API service"
}

# Note: The actual environment variable update will be done via the deployment script
# using AWS CLI to avoid Terraform state conflicts with existing resources