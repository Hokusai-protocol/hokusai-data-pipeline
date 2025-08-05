# Environment configuration for API service to connect to MLflow via service discovery

# Update the API task definition environment variables
# Add this to the aws_ecs_task_definition.api container definition environment section:

/*
environment = [
  {
    name  = "ENVIRONMENT"
    value = var.environment
  },
  {
    name  = "MLFLOW_SERVER_URL"
    value = "http://mlflow.${var.project_name}-${var.environment}.local:5000"
  },
  {
    name  = "MLFLOW_TRACKING_URI"
    value = "http://mlflow.${var.project_name}-${var.environment}.local:5000"
  },
  {
    name  = "AUTH_SERVICE_URL"
    value = "https://auth.hokus.ai"
  },
  {
    name  = "AUTH_SERVICE_ID"
    value = "platform"
  },
  {
    name  = "MLFLOW_PROXY_DEBUG"
    value = "true"  # Enable debug logging for troubleshooting
  }
]
*/

# Example complete environment configuration for API container:
locals {
  api_environment_variables = [
    {
      name  = "ENVIRONMENT"
      value = var.environment
    },
    {
      name  = "MLFLOW_SERVER_URL"
      value = "http://mlflow.${var.project_name}-${var.environment}.local:5000"
    },
    {
      name  = "MLFLOW_TRACKING_URI"
      value = "http://mlflow.${var.project_name}-${var.environment}.local:5000"
    },
    {
      name  = "AUTH_SERVICE_URL"
      value = "https://auth.hokus.ai"
    },
    {
      name  = "AUTH_SERVICE_ID"
      value = "platform"
    },
    {
      name  = "API_HOST"
      value = "0.0.0.0"
    },
    {
      name  = "API_PORT"
      value = "8001"
    },
    {
      name  = "MLFLOW_PROXY_DEBUG"
      value = "true"
    },
    {
      name  = "MLFLOW_SERVE_ARTIFACTS"
      value = "true"
    }
  ]
}