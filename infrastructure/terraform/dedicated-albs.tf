# Dedicated ALBs for Auth and Registry Services
# This configuration creates separate ALBs to eliminate routing conflicts

# ========================================
# DATA SOURCES
# ========================================

# Use the existing VPC from the module
data "aws_vpc" "existing" {
  id = module.vpc.vpc_id
}

# ========================================
# TARGET GROUPS
# ========================================

# Auth Service Target Group
resource "aws_lb_target_group" "auth" {
  name        = "${var.project_name}-auth-ded-${var.environment}"
  port        = 8000  # Update this to match your auth service port
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.existing.id
  target_type = "ip"  # For awsvpc network mode

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 30
    path                = "/health"
    matcher             = "200"
  }

  stickiness {
    type            = "lb_cookie"
    cookie_duration = 86400
    enabled         = true
  }

  tags = {
    Name        = "${var.project_name}-auth-tg"
    Environment = var.environment
    Service     = "auth"
  }
}

# API Service Target Group for Registry ALB
resource "aws_lb_target_group" "registry_api" {
  name        = "${var.project_name}-api-ded-${var.environment}"
  port        = 8001
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.existing.id
  target_type = "ip"  # For awsvpc network mode

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 30
    path                = "/health"
    matcher             = "200"
  }

  stickiness {
    type            = "lb_cookie"
    cookie_duration = 86400
    enabled         = true
  }

  tags = {
    Name        = "${var.project_name}-api-dedicated-tg"
    Environment = var.environment
    Service     = "api"
  }
}

# MLflow Service Target Group for Registry ALB
resource "aws_lb_target_group" "registry_mlflow" {
  name        = "${var.project_name}-mlflow-ded-${var.environment}"
  port        = 5000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.existing.id
  target_type = "ip"  # For awsvpc network mode

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 10
    interval            = 30
    path                = "/health"
    matcher             = "200"
  }

  stickiness {
    type            = "lb_cookie"
    cookie_duration = 86400
    enabled         = true
  }

  tags = {
    Name        = "${var.project_name}-mlflow-dedicated-tg"
    Environment = var.environment
    Service     = "mlflow"
  }
}

# ========================================
# AUTH SERVICE ALB
# ========================================

resource "aws_lb" "auth" {
  name               = "${var.project_name}-auth-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets           = module.vpc.public_subnets

  enable_deletion_protection = var.environment == "production" ? true : false
  enable_http2              = true

  tags = {
    Name        = "${var.project_name}-auth-alb"
    Environment = var.environment
    Service     = "auth"
  }
}

# HTTP Listener for Auth (redirects to HTTPS)
resource "aws_lb_listener" "auth_http" {
  load_balancer_arn = aws_lb.auth.arn
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

# HTTPS Listener for Auth
resource "aws_lb_listener" "auth_https" {
  count = var.certificate_arn != "" ? 1 : 0
  
  load_balancer_arn = aws_lb.auth.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.auth.arn
  }
}

# Auth API v1 routing rule
resource "aws_lb_listener_rule" "auth_api_v1" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.auth_https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.auth.arn
  }

  condition {
    path_pattern {
      values = ["/api/v1/*"]
    }
  }
}

# Auth health check rule
resource "aws_lb_listener_rule" "auth_health" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.auth_https[0].arn
  priority     = 90

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.auth.arn
  }

  condition {
    path_pattern {
      values = ["/health", "/"]
    }
  }
}

# ========================================
# REGISTRY SERVICE ALB
# ========================================

resource "aws_lb" "registry" {
  name               = "${var.project_name}-registry-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets           = module.vpc.public_subnets

  enable_deletion_protection = var.environment == "production" ? true : false
  enable_http2              = true

  tags = {
    Name        = "${var.project_name}-registry-alb"
    Environment = var.environment
    Service     = "registry"
  }
}

# HTTP Listener for Registry (redirects to HTTPS)
resource "aws_lb_listener" "registry_http" {
  load_balancer_arn = aws_lb.registry.arn
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

# HTTPS Listener for Registry
resource "aws_lb_listener" "registry_https" {
  count = var.certificate_arn != "" ? 1 : 0
  
  load_balancer_arn = aws_lb.registry.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.registry_api.arn
  }
}

# Registry MLflow routing rule
resource "aws_lb_listener_rule" "dedicated_registry_mlflow" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.registry_https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.registry_mlflow.arn
  }

  condition {
    path_pattern {
      values = ["/mlflow", "/mlflow/*"]
    }
  }
}

# Registry API MLflow proxy routing
resource "aws_lb_listener_rule" "dedicated_registry_api_mlflow" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.registry_https[0].arn
  priority     = 110

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.registry_api.arn
  }

  condition {
    path_pattern {
      values = ["/api/mlflow/*"]
    }
  }
}

# Registry API general routing
resource "aws_lb_listener_rule" "dedicated_registry_api" {
  count = var.certificate_arn != "" ? 1 : 0
  
  listener_arn = aws_lb_listener.registry_https[0].arn
  priority     = 120

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.registry_api.arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}

# ========================================
# OUTPUTS
# ========================================

output "auth_alb_dns" {
  description = "DNS name of the auth ALB"
  value       = aws_lb.auth.dns_name
}

output "auth_alb_zone_id" {
  description = "Zone ID of the auth ALB"
  value       = aws_lb.auth.zone_id
}

output "registry_alb_dns" {
  description = "DNS name of the registry ALB"
  value       = aws_lb.registry.dns_name
}

output "registry_alb_zone_id" {
  description = "Zone ID of the registry ALB"
  value       = aws_lb.registry.zone_id
}

# ========================================
# ROUTE53 DNS CONFIGURATION
# ========================================

# Auth subdomain
resource "aws_route53_record" "auth" {
  count = var.route53_zone_id != "" ? 1 : 0
  
  zone_id = var.route53_zone_id
  name    = "auth.hokus.ai"
  type    = "A"

  alias {
    name                   = aws_lb.auth.dns_name
    zone_id                = aws_lb.auth.zone_id
    evaluate_target_health = true
  }
}

# Registry subdomain
resource "aws_route53_record" "registry" {
  count = var.route53_zone_id != "" ? 1 : 0
  
  zone_id = var.route53_zone_id
  name    = "registry.hokus.ai"
  type    = "A"

  alias {
    name                   = aws_lb.registry.dns_name
    zone_id                = aws_lb.registry.zone_id
    evaluate_target_health = true
  }
}

# ========================================
# REQUIRED VARIABLES
# ========================================
# Add these to your variables.tf if not already present:
#
# variable "vpc_id" {
#   description = "VPC ID for the ALBs (leave empty to use default VPC)"
#   type        = string
#   default     = ""
# }
#
# variable "route53_zone_id" {
#   description = "Route53 Hosted Zone ID for DNS records"
#   type        = string
#   default     = ""
# }

# ========================================
# MIGRATION NOTICE
# ========================================
# After applying this configuration:
# 1. Update DNS records to point to new ALBs
# 2. Test all endpoints thoroughly
# 3. Remove old shared ALB configuration from main.tf
# 4. Update application configurations with new endpoints