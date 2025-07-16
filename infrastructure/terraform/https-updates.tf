# HTTPS Configuration Updates for Hokusai Platform
# This file contains the necessary updates to enable HTTPS

# Update the existing HTTP listener to redirect to HTTPS
# NOTE: This overwrites the existing aws_lb_listener.http resource in main.tf
# When certificate_arn is provided, this configuration should be applied

# HTTP to HTTPS Redirect Listener
resource "aws_lb_listener" "http_redirect" {
  count = var.certificate_arn != "" ? 1 : 0
  
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"
  
  default_action {
    type = "redirect"
    
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# HTTPS Listener Rules for API
resource "aws_lb_listener_rule" "https_api" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.https[0].arn
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

# HTTPS Listener Rules for registry.hokus.ai - MLflow
resource "aws_lb_listener_rule" "https_registry_mlflow" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 40
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.mlflow.arn
  }
  
  condition {
    host_header {
      values = ["registry.hokus.ai"]
    }
  }
  
  condition {
    path_pattern {
      values = ["/mlflow", "/mlflow/*"]
    }
  }
}

# HTTPS Listener Rules for registry.hokus.ai - API
resource "aws_lb_listener_rule" "https_registry_api" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 50
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    host_header {
      values = ["registry.hokus.ai"]
    }
  }
}

# HTTPS Listener Rules for MLflow
resource "aws_lb_listener_rule" "https_mlflow" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 200
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.mlflow.arn
  }
  
  condition {
    path_pattern {
      values = ["/mlflow", "/mlflow/*"]
    }
  }
}

# Certificate Expiration Monitoring
resource "aws_cloudwatch_metric_alarm" "certificate_expiry" {
  count = var.certificate_arn != "" ? 1 : 0
  
  alarm_name          = "${var.project_name}-certificate-expiry-${var.environment}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "DaysToExpiry"
  namespace           = "AWS/CertificateManager"
  period              = "86400"
  statistic           = "Average"
  threshold           = "30"
  alarm_description   = "Alert when SSL certificate expires in less than 30 days"
  treat_missing_data  = "breaching"
  
  dimensions = {
    CertificateArn = var.certificate_arn
  }
  
  alarm_actions = [aws_sns_topic.alerts.arn]
}

# Update task definitions to use HTTPS URLs
locals {
  api_base_url = var.certificate_arn != "" ? "https://api.hokus.ai" : "http://api.hokus.ai"
  mlflow_url   = var.certificate_arn != "" ? "https://registry.hokus.ai/mlflow" : "http://registry.hokus.ai/mlflow"
}

# Additional outputs for HTTPS endpoints
output "https_api_endpoint" {
  description = "HTTPS endpoint for API"
  value       = var.certificate_arn != "" ? "https://${aws_lb.main.dns_name}" : "Not configured - certificate required"
}

output "https_api_domain" {
  description = "HTTPS domain for API"
  value       = var.certificate_arn != "" ? "https://api.hokus.ai" : "Not configured - certificate required"
}