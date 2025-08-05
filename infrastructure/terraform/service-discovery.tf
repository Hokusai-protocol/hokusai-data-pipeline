# Service Discovery Configuration for internal service communication

# Create a private DNS namespace for service discovery
resource "aws_service_discovery_private_dns_namespace" "internal" {
  name        = "${var.project_name}-${var.environment}.local"
  description = "Private DNS namespace for ${var.project_name} services"
  vpc         = module.vpc.vpc_id
}

# Service discovery for MLflow
resource "aws_service_discovery_service" "mlflow" {
  name = "mlflow"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.internal.id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# Service discovery for API service
resource "aws_service_discovery_service" "api" {
  name = "api"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.internal.id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# Note: The ECS services in main.tf need to be updated with service_registries blocks
# to register with these service discovery services.

# Output the internal DNS name for MLflow
output "mlflow_internal_dns" {
  value       = "mlflow.${aws_service_discovery_private_dns_namespace.internal.name}"
  description = "Internal DNS name for MLflow service"
}