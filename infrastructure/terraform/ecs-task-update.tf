# ECS Task Definition Updates for Service Degradation Fix
# This file updates resource limits and health check configurations

# Updated Registry API Task Definition
resource "aws_ecs_task_definition" "registry_api" {
  family                   = "hokusai-registry-api-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"  # Increased from 512
  memory                   = "2048"  # Increased from 1024
  execution_role_arn       = var.ecs_execution_role_arn
  task_role_arn           = var.ecs_task_role_arn

  container_definitions = jsonencode([
    {
      name  = "api"
      image = "${var.ecr_repository_url}:latest"
      
      # Increased resource limits
      cpu    = 1024
      memory = 2048
      
      # Health check configuration
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health/live || exit 1"]
        interval    = 30
        timeout     = 10
        retries     = 3
        startPeriod = 60  # Give service time to start
      }

      # Environment variables for circuit breaker
      environment = [
        {
          name  = "CIRCUIT_BREAKER_FAILURE_THRESHOLD"
          value = "5"
        },
        {
          name  = "CIRCUIT_BREAKER_RECOVERY_TIMEOUT"
          value = "30"
        },
        {
          name  = "CIRCUIT_BREAKER_EXPECTED_EXCEPTION"
          value = "ConnectionError,TimeoutError"
        },
        {
          name  = "MLFLOW_TRACKING_URI"
          value = "http://mlflow.hokusai-dev.local:5000"
        },
        {
          name  = "HEALTH_CHECK_TIMEOUT"
          value = "5"
        },
        {
          name  = "ENABLE_AUTO_RECOVERY"
          value = "true"
        }
      ]

      # Logging configuration
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/hokusai-registry-${var.environment}"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      # Stop timeout for graceful shutdown
      stopTimeout = 30
    }
  ])

  tags = {
    Name        = "hokusai-registry-api-task"
    Environment = var.environment
    Service     = "registry"
    Purpose     = "Service degradation fix"
  }
}

# Updated MLflow Task Definition
resource "aws_ecs_task_definition" "mlflow" {
  family                   = "hokusai-mlflow-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "2048"  # Increased for MLflow performance
  memory                   = "4096"  # Increased for artifact handling
  execution_role_arn       = var.ecs_execution_role_arn
  task_role_arn           = var.ecs_task_role_arn

  container_definitions = jsonencode([
    {
      name  = "mlflow"
      image = "${var.mlflow_ecr_repository_url}:latest"
      
      cpu    = 2048
      memory = 4096
      
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:5000/health || exit 1"]
        interval    = 60
        timeout     = 15
        retries     = 5
        startPeriod = 120  # MLflow needs more startup time
      }

      environment = [
        {
          name  = "BACKEND_STORE_URI"
          value = "postgresql://${var.db_username}:${var.db_password}@${var.db_endpoint}/${var.db_name}"
        },
        {
          name  = "DEFAULT_ARTIFACT_ROOT"
          value = "s3://${var.mlflow_artifacts_bucket}/artifacts"
        },
        {
          name  = "MLFLOW_SERVER_HOST"
          value = "0.0.0.0"
        },
        {
          name  = "MLFLOW_SERVER_PORT"
          value = "5000"
        },
        {
          name  = "MLFLOW_SERVER_WORKERS"
          value = "4"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/hokusai-mlflow-${var.environment}"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "mlflow"
        }
      }

      portMappings = [
        {
          containerPort = 5000
          protocol      = "tcp"
        }
      ]

      stopTimeout = 60  # More time for graceful shutdown
    }
  ])

  tags = {
    Name        = "hokusai-mlflow-task"
    Environment = var.environment
    Service     = "mlflow"
    Purpose     = "Service degradation fix"
  }
}

# ECS Service Updates
resource "aws_ecs_service" "registry_api" {
  name            = "hokusai-registry-api-${var.environment}"
  cluster         = var.ecs_cluster_id
  task_definition = aws_ecs_task_definition.registry_api.arn
  desired_count   = 2  # Increased for redundancy
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [var.ecs_security_group_id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.registry_api.arn
    container_name   = "api"
    container_port   = 8000
  }

  service_registries {
    registry_arn = aws_service_discovery_service.registry_api.arn
  }

  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100  # Ensure zero downtime
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  tags = {
    Name        = "hokusai-registry-api-service"
    Environment = var.environment
    Service     = "registry"
  }
}

resource "aws_ecs_service" "mlflow" {
  name            = "hokusai-mlflow-${var.environment}"
  cluster         = var.ecs_cluster_id
  task_definition = aws_ecs_task_definition.mlflow.arn
  desired_count   = 2  # Increased for redundancy
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [var.ecs_security_group_id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.mlflow.arn
    container_name   = "mlflow"
    container_port   = 5000
  }

  service_registries {
    registry_arn = aws_service_discovery_service.mlflow.arn
  }

  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  tags = {
    Name        = "hokusai-mlflow-service"
    Environment = var.environment
    Service     = "mlflow"
  }
}

# Service Discovery for internal communication
resource "aws_service_discovery_service" "registry_api" {
  name = "registry"

  dns_config {
    namespace_id = var.service_discovery_namespace_id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 2
  }
}

resource "aws_service_discovery_service" "mlflow" {
  name = "mlflow"

  dns_config {
    namespace_id = var.service_discovery_namespace_id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 2
  }
}