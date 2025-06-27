# AWS Configuration
aws_region = "us-east-1"
environment = "development"  # Options: development, staging, production
project_name = "hokusai"

# Network Configuration
vpc_cidr = "10.0.0.0/16"
private_subnet_cidrs = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
public_subnet_cidrs = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

# Database Configuration
# CHANGE_ME: Use a strong password for production
database_password = "YcAhadh5KTR/EuRta9Da3ddgplkvQ35X/1ICAurSr+k="
db_instance_class = "db.t3.micro"  # Use larger instance for production

# API Configuration
api_secret_key = "A544iJ7a7GGy9x4fczYdzFrHM"

# Container Configuration
api_image_tag = "latest"
mlflow_image_tag = "latest"
api_cpu = 256
api_memory = 512
mlflow_cpu = 512
mlflow_memory = 1024

# Scaling Configuration
api_desired_count = 2
mlflow_desired_count = 1

# Security Configuration
enable_deletion_protection = false  # Set to true for production

# Domain Configuration (optional)
# certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/example"
# domain_name = "ml.hokus.ai"

# Rate Limiting
rate_limit_requests = 100
rate_limit_period = 60

# Access Control (optional)
# allowed_ips = ["1.2.3.4/32", "5.6.7.8/32"]  # Restrict to specific IPs
# admin_eth_addresses = ["0xa7aAD9938043648218aa0512383e32d53C82D878"]

# Additional Tags
tags = {
  Owner = "hokusai"
  CostCenter = "ml-platform"
}