# Example Terraform variables file for Hokusai infrastructure
# Copy this to terraform.tfvars and fill in your values

# Required variables
environment = "development"  # or "staging", "production"
database_password = "your-secure-database-password"
api_secret_key = "your-secure-api-secret-key"

# HTTPS Configuration
# To enable HTTPS, provide the ARN of your ACM certificate
# Leave empty to use HTTP only
certificate_arn = "arn:aws:acm:us-east-1:932100697590:certificate/286ebcb3-218a-4f4d-8698-f70f283d51b4"

# Optional: Domain configuration
domain_name = "hokus.ai"

# Optional: Resource sizing
api_cpu = 256
api_memory = 512
api_desired_count = 2

mlflow_cpu = 512
mlflow_memory = 1024
mlflow_desired_count = 1

db_instance_class = "db.t3.micro"

# Optional: Security settings
rate_limit_requests = 100
rate_limit_period = 60

# Optional: Admin ETH addresses for special permissions
admin_eth_addresses = [
  # "0x1234567890123456789012345678901234567890",
]

# Optional: IP allowlist (empty allows all)
allowed_ips = []

# Optional: Additional tags
tags = {
  Team = "MLOps"
  CostCenter = "Engineering"
}