variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (e.g., production, staging, development)"
  type        = string
  validation {
    condition     = contains(["production", "staging", "development"], var.environment)
    error_message = "Environment must be production, staging, or development."
  }
}

variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "hokusai"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
}

variable "database_password" {
  description = "Password for RDS PostgreSQL database"
  type        = string
  sensitive   = true
}

variable "api_secret_key" {
  description = "Secret key for API authentication"
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "api_image_tag" {
  description = "Docker image tag for API service"
  type        = string
  default     = "latest"
}

variable "mlflow_image_tag" {
  description = "Docker image tag for MLflow service"
  type        = string
  default     = "latest"
}

variable "api_cpu" {
  description = "CPU units for API service"
  type        = number
  default     = 256
}

variable "api_memory" {
  description = "Memory (MB) for API service"
  type        = number
  default     = 512
}

variable "mlflow_cpu" {
  description = "CPU units for MLflow service"
  type        = number
  default     = 512
}

variable "mlflow_memory" {
  description = "Memory (MB) for MLflow service"
  type        = number
  default     = 1024
}

variable "api_desired_count" {
  description = "Desired number of API service tasks"
  type        = number
  default     = 2
}

variable "mlflow_desired_count" {
  description = "Desired number of MLflow service tasks"
  type        = number
  default     = 1
}

variable "enable_deletion_protection" {
  description = "Enable deletion protection for critical resources"
  type        = bool
  default     = true
}

variable "certificate_arn" {
  description = "ARN of ACM certificate for HTTPS"
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = ""
}

variable "rate_limit_requests" {
  description = "Number of requests allowed per rate limit period"
  type        = number
  default     = 100
}

variable "rate_limit_period" {
  description = "Rate limit period in seconds"
  type        = number
  default     = 60
}

variable "allowed_ips" {
  description = "List of allowed IP addresses for API access (empty list allows all)"
  type        = list(string)
  default     = []
}

variable "admin_eth_addresses" {
  description = "List of Ethereum addresses with admin privileges"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Additional tags to apply to resources"
  type        = map(string)
  default     = {}
}

variable "auth_service_id" {
  description = "Service ID for API key validation (platform or ml-platform)"
  type        = string
  default     = "platform"
}