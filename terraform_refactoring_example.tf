# Example of how to refactor local Terraform to use centralized infrastructure

# Data source to access centralized infrastructure state
data "terraform_remote_state" "infrastructure" {
  backend = "s3"
  config = {
    bucket = "hokusai-infrastructure-tfstate"
    key    = "prod/infrastructure.tfstate"
    region = "us-east-1"
  }
}

# Remove these resources from local terraform (they're now in central infrastructure):
# - aws_lb.main
# - aws_lb.auth  
# - aws_lb.registry
# - aws_lb_target_group.api
# - aws_lb_target_group.mlflow
# - aws_lb_target_group.auth
# - aws_lb_target_group.registry_api
# - aws_lb_target_group.registry_mlflow
# - aws_lb_listener.* (all listeners)
# - aws_lb_listener_rule.* (all routing rules)
# - aws_route53_record.auth
# - aws_route53_record.registry
# - aws_iam_role.ecs_task_execution
# - aws_iam_role.ecs_task
# - aws_security_group.alb

# Update ECS service to reference remote infrastructure
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
    # Reference target group from remote state instead of local resource
    target_group_arn = data.terraform_remote_state.infrastructure.outputs.api_target_group_arn
    container_name   = "${var.project_name}-api"
    container_port   = 8001
  }
  
  # Reference listener from remote state
  depends_on = [data.terraform_remote_state.infrastructure]
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
    # Reference target group from remote state
    target_group_arn = data.terraform_remote_state.infrastructure.outputs.mlflow_target_group_arn
    container_name   = "${var.project_name}-mlflow"
    container_port   = 5000
  }
  
  depends_on = [data.terraform_remote_state.infrastructure]
}

# Update task definitions to use remote IAM roles
resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project_name}-api-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  
  # Reference IAM roles from remote state
  execution_role_arn = data.terraform_remote_state.infrastructure.outputs.ecs_task_execution_role_arn
  task_role_arn     = data.terraform_remote_state.infrastructure.outputs.ecs_task_role_arn
  
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
          name  = "MLFLOW_TRACKING_URI"
          value = "https://${data.terraform_remote_state.infrastructure.outputs.registry_dns_name}/mlflow"
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
    }
  ])
}

# Update security group to allow traffic from ALB
resource "aws_security_group" "ecs_tasks" {
  name_prefix = "${var.project_name}-ecs-tasks-"
  description = "Security group for ECS tasks"
  vpc_id      = module.vpc.vpc_id
  
  ingress {
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    # Reference ALB security group from remote state
    security_groups = [data.terraform_remote_state.infrastructure.outputs.alb_security_group_id]
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

# Update outputs to reference remote infrastructure
output "api_endpoint" {
  description = "URL for the API endpoint"
  value       = "https://${data.terraform_remote_state.infrastructure.outputs.registry_dns_name}/api"
}

output "mlflow_endpoint" {
  description = "URL for the MLflow UI"
  value       = "https://${data.terraform_remote_state.infrastructure.outputs.registry_dns_name}/mlflow"
}

output "main_alb_dns" {
  description = "DNS name of the main ALB"
  value       = data.terraform_remote_state.infrastructure.outputs.main_alb_dns_name
}