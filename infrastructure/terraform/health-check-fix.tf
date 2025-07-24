# Health Check Configuration Updates for Deployment Stability

# Update API service with proper health check grace period
resource "aws_ecs_service" "api_health_fix" {
  # This is an override of the existing service with health check improvements
  name            = "${var.project_name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  
  launch_type = "FARGATE"
  
  # Add health check grace period to allow services to start
  health_check_grace_period_seconds = 120
  
  # Enable deployment circuit breaker
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  
  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
    
    deployment_circuit_breaker {
      enable   = true
      rollback = true
    }
  }
  
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
  
  depends_on = [aws_lb_listener.http]
  
  lifecycle {
    create_before_destroy = true
  }
}

# Update MLflow service with proper health check grace period
resource "aws_ecs_service" "mlflow_health_fix" {
  # This is an override of the existing service with health check improvements
  name            = "${var.project_name}-mlflow"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.mlflow.arn
  desired_count   = var.mlflow_desired_count
  
  launch_type = "FARGATE"
  
  # Add health check grace period to allow services to start
  health_check_grace_period_seconds = 120
  
  # Enable deployment circuit breaker
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  
  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
    
    deployment_circuit_breaker {
      enable   = true
      rollback = true
    }
  }
  
  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }
  
  load_balancer {
    target_group_arn = aws_lb_target_group.mlflow.arn
    container_name   = "${var.project_name}-mlflow"
    container_port   = 5000
  }
  
  depends_on = [aws_lb_listener.http]
  
  lifecycle {
    create_before_destroy = true
  }
}

# Update target group health check settings for API
resource "aws_lb_target_group" "api_health_fix" {
  name        = "${var.project_name}-api-${var.environment}"
  port        = 8001
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip"
  
  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 10      # Increased from 5 to 10 seconds
    unhealthy_threshold = 3       # Increased from 2 to 3
  }
  
  # Increase deregistration delay for graceful shutdown
  deregistration_delay = 60       # Increased from 30 to 60 seconds
  
  lifecycle {
    create_before_destroy = true
  }
}

# Update target group health check settings for MLflow
resource "aws_lb_target_group" "mlflow_health_fix" {
  name        = "${var.project_name}-mlflow-${var.environment}"
  port        = 5000
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip"
  
  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200,308"
    path                = "/mlflow"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 10      # Increased from 5 to 10 seconds
    unhealthy_threshold = 3       # Increased from 2 to 3
  }
  
  # Increase deregistration delay for graceful shutdown
  deregistration_delay = 60       # Increased from 30 to 60 seconds
  
  lifecycle {
    create_before_destroy = true
  }
}