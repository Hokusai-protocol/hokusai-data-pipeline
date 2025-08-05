# ECS Service Updates for Service Discovery
# This file contains the updated ECS service configurations with service discovery registration
# Apply these changes to the main.tf file

# Updated API Service with Service Discovery
resource "aws_ecs_service" "api_with_discovery" {
  name            = "${var.project_name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  
  launch_type = "FARGATE"
  
  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }
  
  load_balancer {
    target_group_arn = aws_lb_target_group.registry_api.arn
    container_name   = "${var.project_name}-api"
    container_port   = 8001
  }
  
  # Service Discovery Registration
  service_registries {
    registry_arn = aws_service_discovery_service.api.arn
  }
  
  depends_on = [aws_lb_listener.registry_https]
}

# Updated MLflow Service with Service Discovery
resource "aws_ecs_service" "mlflow_with_discovery" {
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
    target_group_arn = aws_lb_target_group.registry_mlflow.arn
    container_name   = "${var.project_name}-mlflow"
    container_port   = 5000
  }
  
  # Service Discovery Registration
  service_registries {
    registry_arn = aws_service_discovery_service.mlflow.arn
  }
  
  depends_on = [aws_lb_listener.registry_https]
}

# Note: After applying these changes:
# 1. The API service will be accessible internally at: api.hokusai-development.local:8001
# 2. The MLflow service will be accessible internally at: mlflow.hokusai-development.local:5000
# 3. Update the MLFLOW_SERVER_URL environment variable in the API service to use the service discovery DNS name