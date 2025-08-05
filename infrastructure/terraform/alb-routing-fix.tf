# ALB Routing Fix for PR #60 Enhancements
# This file contains the updated routing rules to fix conflicts and enable all MLflow paths

# Remove the old broad API rule by commenting it out in main.tf
# and add these more specific rules

# API MLflow proxy rule - handles /api/mlflow/* requests
resource "aws_lb_listener_rule" "api_mlflow_proxy" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 60
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    host_header {
      values = ["registry.hokus.ai"]
    }
  }
  
  condition {
    path_pattern {
      values = ["/api/mlflow/*"]
    }
  }
}

# API health check rule - handles /api/health/* requests
resource "aws_lb_listener_rule" "api_health" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 70
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    host_header {
      values = ["registry.hokus.ai"]
    }
  }
  
  condition {
    path_pattern {
      values = ["/api/health/*"]
    }
  }
}

# Update the general API rule to be more specific
resource "aws_lb_listener_rule" "registry_api_general" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 80
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    host_header {
      values = ["registry.hokus.ai"]
    }
  }
  
  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}

# HTTPS versions of the same rules (when certificate is configured)
resource "aws_lb_listener_rule" "api_mlflow_proxy_https" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 60
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    host_header {
      values = ["registry.hokus.ai"]
    }
  }
  
  condition {
    path_pattern {
      values = ["/api/mlflow/*"]
    }
  }
}

resource "aws_lb_listener_rule" "api_health_https" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 70
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    host_header {
      values = ["registry.hokus.ai"]
    }
  }
  
  condition {
    path_pattern {
      values = ["/api/health/*"]
    }
  }
}

resource "aws_lb_listener_rule" "registry_api_general_https" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 80
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    host_header {
      values = ["registry.hokus.ai"]
    }
  }
  
  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}

# Also need to add HTTPS listener if it doesn't exist
resource "aws_lb_listener" "https" {
  count = var.certificate_arn != "" ? 1 : 0
  
  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.certificate_arn
  
  default_action {
    type = "fixed-response"
    
    fixed_response {
      content_type = "text/plain"
      message_body = "Not Found"
      status_code  = "404"
    }
  }
}

# Copy the existing routing rules to HTTPS
resource "aws_lb_listener_rule" "registry_mlflow_https" {
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

resource "aws_lb_listener_rule" "registry_api_https" {
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

resource "aws_lb_listener_rule" "mlflow_https" {
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