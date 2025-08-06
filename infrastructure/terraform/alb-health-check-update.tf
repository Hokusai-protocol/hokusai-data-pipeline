# ALB Health Check Configuration Updates for Service Degradation Fix
# This file updates the health check parameters to prevent false unhealthy states

# Update Registry ALB Target Group Health Check
resource "aws_lb_target_group" "registry_api" {
  name        = "hokusai-registry-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2    # Reduced from 3 for faster recovery
    unhealthy_threshold = 3    # Increased from 2 for more tolerance
    timeout             = 10   # Increased from 5 seconds
    interval            = 30   # Standard interval
    path                = "/health/live"  # Changed from /ready to /live for infrastructure health
    matcher             = "200-299"       # Accept any 2xx status
    port                = "traffic-port"
  }

  deregistration_delay = 30  # Reduced from 60 for faster updates

  stickiness {
    type            = "lb_cookie"
    enabled         = true
    cookie_duration = 86400
  }

  tags = {
    Name        = "hokusai-registry-api-tg"
    Environment = var.environment
    Service     = "registry"
    Purpose     = "Service degradation fix"
  }
}

# Update MLflow Target Group Health Check
resource "aws_lb_target_group" "mlflow" {
  name        = "hokusai-mlflow-tg"
  port        = 5000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2    # Reduced for faster recovery
    unhealthy_threshold = 5    # Very tolerant of transient issues
    timeout             = 15   # Generous timeout for MLflow startup
    interval            = 60   # Longer interval to reduce load
    path                = "/health"
    matcher             = "200-299"
    port                = "traffic-port"
  }

  deregistration_delay = 30

  tags = {
    Name        = "hokusai-mlflow-tg"
    Environment = var.environment
    Service     = "mlflow"
    Purpose     = "Service degradation fix"
  }
}

# CloudWatch Alarms for Health Check Failures
resource "aws_cloudwatch_metric_alarm" "registry_unhealthy_targets" {
  alarm_name          = "hokusai-registry-unhealthy-targets"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = "60"
  statistic           = "Average"
  threshold           = "0"
  alarm_description   = "Alert when registry has unhealthy targets"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    TargetGroup  = aws_lb_target_group.registry_api.arn_suffix
    LoadBalancer = var.registry_alb_arn_suffix
  }

  tags = {
    Name        = "registry-health-alarm"
    Environment = var.environment
    Service     = "registry"
  }
}

resource "aws_cloudwatch_metric_alarm" "mlflow_unhealthy_targets" {
  alarm_name          = "hokusai-mlflow-unhealthy-targets"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "3"  # More tolerant for MLflow
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = "60"
  statistic           = "Average"
  threshold           = "0"
  alarm_description   = "Alert when MLflow has unhealthy targets"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    TargetGroup  = aws_lb_target_group.mlflow.arn_suffix
    LoadBalancer = var.registry_alb_arn_suffix
  }

  tags = {
    Name        = "mlflow-health-alarm"
    Environment = var.environment
    Service     = "mlflow"
  }
}

# Auto-scaling based on health metrics
resource "aws_appautoscaling_policy" "registry_health_based_scaling" {
  name               = "registry-health-based-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = "service/${var.ecs_cluster_name}/hokusai-registry-${var.environment}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  target_tracking_scaling_policy_configuration {
    target_value = 1.0  # Target 1 healthy host minimum

    customized_metric_specification {
      metric_name = "HealthyHostCount"
      namespace   = "AWS/ApplicationELB"
      statistic   = "Average"

      dimensions {
        name  = "TargetGroup"
        value = aws_lb_target_group.registry_api.arn_suffix
      }

      dimensions {
        name  = "LoadBalancer"
        value = var.registry_alb_arn_suffix
      }
    }

    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# Outputs for verification
output "registry_target_group_arn" {
  value       = aws_lb_target_group.registry_api.arn
  description = "ARN of the registry target group with updated health checks"
}

output "mlflow_target_group_arn" {
  value       = aws_lb_target_group.mlflow.arn
  description = "ARN of the MLflow target group with updated health checks"
}

output "health_check_endpoints" {
  value = {
    registry = "${aws_lb_target_group.registry_api.health_check[0].path}"
    mlflow   = "${aws_lb_target_group.mlflow.health_check[0].path}"
  }
  description = "Health check endpoints being used"
}