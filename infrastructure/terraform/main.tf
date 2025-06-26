terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  backend "s3" {
    # Backend configuration will be provided via backend config file
    # or terraform init -backend-config options
  }
}

provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# VPC Configuration
module "vpc" {
  source = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"
  
  name = "${var.project_name}-${var.environment}-vpc"
  cidr = var.vpc_cidr
  
  azs             = data.aws_availability_zones.available.names
  private_subnets = var.private_subnet_cidrs
  public_subnets  = var.public_subnet_cidrs
  
  enable_nat_gateway = true
  single_nat_gateway = var.environment != "production"
  enable_dns_hostnames = true
  enable_dns_support   = true
  
  tags = {
    Name = "${var.project_name}-${var.environment}-vpc"
  }
}

# Security Groups
resource "aws_security_group" "alb" {
  name_prefix = "${var.project_name}-alb-"
  description = "Security group for Application Load Balancer"
  vpc_id      = module.vpc.vpc_id
  
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "ecs_tasks" {
  name_prefix = "${var.project_name}-ecs-tasks-"
  description = "Security group for ECS tasks"
  vpc_id      = module.vpc.vpc_id
  
  ingress {
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "rds" {
  name_prefix = "${var.project_name}-rds-"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = module.vpc.vpc_id
  
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }
  
  lifecycle {
    create_before_destroy = true
  }
}

# S3 Buckets
resource "aws_s3_bucket" "mlflow_artifacts" {
  bucket = "hokusai-mlflow-artifacts-${var.environment}"
  
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "mlflow_artifacts" {
  bucket = aws_s3_bucket.mlflow_artifacts.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "mlflow_artifacts" {
  bucket = aws_s3_bucket.mlflow_artifacts.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "mlflow_artifacts" {
  bucket = aws_s3_bucket.mlflow_artifacts.id
  
  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

resource "aws_s3_bucket" "pipeline_data" {
  bucket = "hokusai-pipeline-data-${var.environment}"
  
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "pipeline_data" {
  bucket = aws_s3_bucket.pipeline_data.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "pipeline_data" {
  bucket = aws_s3_bucket.pipeline_data.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# RDS PostgreSQL
resource "aws_db_subnet_group" "mlflow" {
  name       = "${var.project_name}-mlflow-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_db_parameter_group" "mlflow" {
  name   = "${var.project_name}-mlflow-${var.environment}"
  family = "postgres15"
  
  parameter {
    name  = "log_connections"
    value = "1"
  }
}

resource "aws_db_instance" "mlflow" {
  identifier = "${var.project_name}-mlflow-${var.environment}"
  
  engine         = "postgres"
  engine_version = "15.7"
  instance_class = var.db_instance_class
  
  allocated_storage     = 20
  max_allocated_storage = 100
  storage_encrypted     = true
  
  db_name  = "mlflow_db"
  username = "mlflow"
  password = var.database_password
  
  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.mlflow.name
  parameter_group_name   = aws_db_parameter_group.mlflow.name
  
  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"
  
  multi_az               = var.environment == "production"
  deletion_protection    = var.environment == "production"
  skip_final_snapshot    = var.environment != "production"
  
  enabled_cloudwatch_logs_exports = ["postgresql"]
}

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}"
  
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name
  
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
  
  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }
}

# Application Load Balancer
resource "aws_lb" "main" {
  name               = "${var.project_name}-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets           = module.vpc.public_subnets
  
  enable_deletion_protection = var.environment == "production"
  enable_http2              = true
}

resource "aws_lb_target_group" "api" {
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
    timeout             = 5
    unhealthy_threshold = 2
  }
  
  deregistration_delay = 30
}

resource "aws_lb_target_group" "mlflow" {
  name        = "${var.project_name}-mlflow-${var.environment}"
  port        = 5000
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
    timeout             = 5
    unhealthy_threshold = 2
  }
  
  deregistration_delay = 30
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"
  
  default_action {
    type = "fixed-response"
    
    fixed_response {
      content_type = "text/plain"
      message_body = "Not Found"
      status_code  = "404"
    }
  }
}

# API listener rule
resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 100
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    path_pattern {
      values = ["/api*"]
    }
  }
}

# MLflow listener rule
resource "aws_lb_listener_rule" "mlflow" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 200
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.mlflow.arn
  }
  
  condition {
    path_pattern {
      values = ["/mlflow*"]
    }
  }
}

# IAM Roles
resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-ecs-execution-${var.environment}"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-ecs-task-${var.environment}"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "ecs_task_s3" {
  name = "${var.project_name}-ecs-s3-${var.environment}"
  role = aws_iam_role.ecs_task.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.mlflow_artifacts.arn,
          "${aws_s3_bucket.mlflow_artifacts.arn}/*",
          aws_s3_bucket.pipeline_data.arn,
          "${aws_s3_bucket.pipeline_data.arn}/*"
        ]
      }
    ]
  })
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project_name}/api/${var.environment}"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "mlflow" {
  name              = "/ecs/${var.project_name}/mlflow/${var.environment}"
  retention_in_days = 30
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "api_health" {
  alarm_name          = "${var.project_name}-api-health-${var.environment}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "HealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = "60"
  statistic           = "Average"
  threshold           = "1"
  alarm_description   = "This metric monitors API health"
  treat_missing_data  = "breaching"
  
  dimensions = {
    TargetGroup  = aws_lb_target_group.api.arn_suffix
    LoadBalancer = aws_lb.main.arn_suffix
  }
  
  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.project_name}-rds-cpu-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "This metric monitors RDS CPU utilization"
  
  dimensions = {
    DBInstanceIdentifier = aws_db_instance.mlflow.id
  }
  
  alarm_actions = [aws_sns_topic.alerts.arn]
}

# SNS Topic for Alerts
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts-${var.environment}"
}

# Secrets Manager
resource "aws_secretsmanager_secret" "api_keys" {
  name = "${var.project_name}/api-keys/${var.environment}"
  description = "API keys for Hokusai platform"
  
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_secretsmanager_secret" "app_secrets" {
  name = "${var.project_name}/app-secrets/${var.environment}"
  description = "Application secrets for Hokusai platform"
  
  lifecycle {
    prevent_destroy = true
  }
}

# ECS Task Definitions
resource "aws_ecs_task_definition" "api" {
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
          value = "http://${aws_lb.mlflow_internal.dns_name}:5000"
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
}

resource "aws_ecs_task_definition" "mlflow" {
  family                   = "${var.project_name}-mlflow-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.mlflow_cpu
  memory                   = var.mlflow_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn           = aws_iam_role.ecs_task.arn
  
  container_definitions = jsonencode([
    {
      name  = "${var.project_name}-mlflow"
      image = "${aws_ecr_repository.mlflow.repository_url}:${var.mlflow_image_tag}"
      
      portMappings = [
        {
          containerPort = 5000
          protocol      = "tcp"
        }
      ]
      
      environment = [
        {
          name  = "ENVIRONMENT"
          value = var.environment
        },
        {
          name  = "BACKEND_STORE_URI"
          value = "postgresql://mlflow:${var.database_password}@${aws_db_instance.mlflow.endpoint}/mlflow_db"
        },
        {
          name  = "DEFAULT_ARTIFACT_ROOT"
          value = "s3://${aws_s3_bucket.mlflow_artifacts.id}/artifacts"
        }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.mlflow.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:5000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])
}

# ECS Services
resource "aws_ecs_service" "api" {
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
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "${var.project_name}-api"
    container_port   = 8001
  }
  
  depends_on = [aws_lb_listener.http]
}

resource "aws_ecs_service" "mlflow" {
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
    target_group_arn = aws_lb_target_group.mlflow.arn
    container_name   = "${var.project_name}-mlflow"
    container_port   = 5000
  }
  
  depends_on = [aws_lb_listener.http]
}

# ECR Repositories
resource "aws_ecr_repository" "api" {
  name                 = "${var.project_name}-api"
  image_tag_mutability = "MUTABLE"
  
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "mlflow" {
  name                 = "${var.project_name}-mlflow"
  image_tag_mutability = "MUTABLE"
  
  image_scanning_configuration {
    scan_on_push = true
  }
}

# Internal Load Balancer for MLflow
resource "aws_lb" "mlflow_internal" {
  name               = "${var.project_name}-mlflow-int-${var.environment}"
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets           = module.vpc.private_subnets
}

# Add HTTPS listener (placeholder - requires certificate)
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.certificate_arn != "" ? var.certificate_arn : null
  
  default_action {
    type = "fixed-response"
    
    fixed_response {
      content_type = "text/plain"
      message_body = "Not Found"
      status_code  = "404"
    }
  }
  
  count = var.certificate_arn != "" ? 1 : 0
}

# Data sources
data "aws_availability_zones" "available" {
  state = "available"
}