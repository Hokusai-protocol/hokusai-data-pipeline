# Update API task definition with internal MLflow URL

# Override the API task definition with correct internal URLs
resource "aws_ecs_task_definition" "api_updated" {
  family                   = "${var.project_name}-api-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn           = aws_iam_role.ecs_task.arn
  
  container_definitions = jsonencode([
    {
      name  = "${var.project_name}-api"
      image = "${aws_ecr_repository.api.repository_url}:${var.api_image_tag}"
      
      portMappings = [
        {
          containerPort = 8001
          protocol      = "tcp"
        }
      ]
      
      environment = [
        {
          name  = "ENVIRONMENT"
          value = var.environment
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
          name  = "MLFLOW_TRACKING_URI"
          value = "http://mlflow.${var.project_name}-${var.environment}.local:5000"
        },
        {
          name  = "MLFLOW_SERVER_URL"
          value = "http://mlflow.${var.project_name}-${var.environment}.local:5000"
        },
        {
          name  = "MLFLOW_SERVE_ARTIFACTS"
          value = "true"
        },
        {
          name  = "AUTH_SERVICE_ID"
          value = var.auth_service_id
        },
        {
          name  = "AUTH_SERVICE_URL"
          value = "https://auth.hokus.ai/api"
        },
        {
          name  = "MLFLOW_PROXY_DEBUG"
          value = "true"
        }
      ]
      
      secrets = [
        {
          name      = "SECRET_KEY"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:secret_key::"
        },
        {
          name      = "DATABASE_PASSWORD"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:database_password::"
        }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8001/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  lifecycle {
    create_before_destroy = true
  }
}

# Update the API service to use the new task definition
resource "aws_ecs_service" "api_updated" {
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
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "${var.project_name}-api"
    container_port   = 8001
  }
  
  depends_on = [
    aws_lb_listener.http,
    aws_service_discovery_service.mlflow
  ]

  lifecycle {
    create_before_destroy = true
  }
}