# Routing fix for MLflow API proxy conflict
# This file contains the updated routing rules to resolve the /api* catch-all issue

# IMPORTANT: auth.hokus.ai uses the same ALB and needs /api/* routing
# Add auth-specific rules first
resource "aws_lb_listener_rule" "auth_service_api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 80  # Higher priority than general API rules
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    host_header {
      values = ["auth.hokus.ai"]
    }
  }
  
  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}

# Replace the broad /api* rule with specific API version paths
# Using priority 95 to avoid conflict with existing rule at 100
resource "aws_lb_listener_rule" "api_v1" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 95
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    path_pattern {
      values = [
        "/api/v1/*",      # All v1 API endpoints (dspy, auth, etc.)
        "/api/health",    # Future health endpoint under /api
        "/api/health/*"   # Future health endpoints under /api
      ]
    }
  }
  
  lifecycle {
    # This will replace the existing aws_lb_listener_rule.api resource
    create_before_destroy = true
  }
}

# Add specific rule for MLflow proxy under /api/mlflow
resource "aws_lb_listener_rule" "api_mlflow_proxy" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 90  # Higher priority than api_v1 rule
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn  # Goes to API service which has the proxy
  }
  
  condition {
    path_pattern {
      values = ["/api/mlflow/*"]
    }
  }
}

# HTTPS versions of the same rules
resource "aws_lb_listener_rule" "https_auth_service_api" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 80
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    host_header {
      values = ["auth.hokus.ai"]
    }
  }
  
  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}

resource "aws_lb_listener_rule" "https_api_v1" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 95
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    path_pattern {
      values = [
        "/api/v1/*",
        "/api/health",
        "/api/health/*"
      ]
    }
  }
  
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_lb_listener_rule" "https_api_mlflow_proxy" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 90
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    path_pattern {
      values = ["/api/mlflow/*"]
    }
  }
}

# Note: The old rules in main.tf and https-updates.tf should be removed:
# - aws_lb_listener_rule.api (main.tf line 335)
# - aws_lb_listener_rule.https_api (https-updates.tf line 28)