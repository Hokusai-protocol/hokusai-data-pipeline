# ALB Listener Rules for Data Pipeline Services
# This file contains the listener rules that need to be applied in the centralized infrastructure
# after the ECS services are deployed

# Note: These rules should be added to the hokusai-infrastructure repository
# in the file: environments/data-pipeline-ecs-alb-integration.tf

# The following listener rules need to be created:

# 1. API Service Rules for Main ALB
# Path: /api/* -> API Target Group
# Priority: 100

# 2. MLflow Service Rules for Data Pipeline ALB  
# Path: /mlflow/* -> MLflow Target Group
# Priority: 100

# 3. Registry API Rules for Registry ALB
# Host: registry.hokus.ai
# Path: /* (except /mlflow/*) -> Registry API Target Group
# Priority: 200

# 4. Registry MLflow Rules for Registry ALB
# Host: registry.hokus.ai
# Path: /mlflow/* -> Registry MLflow Target Group
# Priority: 100

# Example configuration for the centralized infrastructure:
/*
resource "aws_lb_listener_rule" "data_pipeline_api" {
  listener_arn = aws_lb_listener.main_https.arn
  priority     = 100
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}

resource "aws_lb_listener_rule" "data_pipeline_mlflow" {
  listener_arn = aws_lb_listener.dp_https.arn
  priority     = 100
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.mlflow.arn
  }
  
  condition {
    path_pattern {
      values = ["/mlflow/*"]
    }
  }
}
*/