output "api_endpoint" {
  description = "URL for the API endpoint"
  value       = "http://registry.hokus.ai/api"
}

output "mlflow_endpoint" {
  description = "URL for the MLflow UI"
  value       = "http://mlflow.hokus.ai/mlflow"
}

output "api_endpoint_alb" {
  description = "API endpoint URL via ALB (direct)"
  value       = "http://${aws_lb.main.dns_name}/api"
}

output "mlflow_endpoint_alb" {
  description = "MLflow UI endpoint URL via ALB (direct)"
  value       = "http://${aws_lb.main.dns_name}/mlflow"
}

output "s3_artifacts_bucket" {
  description = "S3 bucket name for MLflow artifacts"
  value       = aws_s3_bucket.mlflow_artifacts.id
}

output "s3_pipeline_bucket" {
  description = "S3 bucket name for pipeline data"
  value       = aws_s3_bucket.pipeline_data.id
}

output "database_endpoint" {
  description = "RDS database endpoint"
  value       = aws_db_instance.mlflow.endpoint
  sensitive   = true
}

output "database_name" {
  description = "RDS database name"
  value       = aws_db_instance.mlflow.db_name
}

output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = module.vpc.private_subnets
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = module.vpc.public_subnets
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  description = "ARN of the ECS cluster"
  value       = aws_ecs_cluster.main.arn
}

output "api_security_group_id" {
  description = "Security group ID for API tasks"
  value       = aws_security_group.ecs_tasks.id
}

output "alb_security_group_id" {
  description = "Security group ID for ALB"
  value       = aws_security_group.alb.id
}

output "rds_security_group_id" {
  description = "Security group ID for RDS"
  value       = aws_security_group.rds.id
}

output "api_target_group_arn" {
  description = "ARN of API target group"
  value       = aws_lb_target_group.api.arn
}

output "mlflow_target_group_arn" {
  description = "ARN of MLflow target group"
  value       = aws_lb_target_group.mlflow.arn
}

output "ecs_task_execution_role_arn" {
  description = "ARN of ECS task execution role"
  value       = aws_iam_role.ecs_task_execution.arn
}

output "ecs_task_role_arn" {
  description = "ARN of ECS task role"
  value       = aws_iam_role.ecs_task.arn
}

output "sns_alerts_topic_arn" {
  description = "ARN of SNS topic for alerts"
  value       = aws_sns_topic.alerts.arn
}

output "api_keys_secret_arn" {
  description = "ARN of Secrets Manager secret for API keys"
  value       = aws_secretsmanager_secret.api_keys.arn
}

output "app_secrets_arn" {
  description = "ARN of Secrets Manager secret for application secrets"
  value       = aws_secretsmanager_secret.app_secrets.arn
}

output "cloudwatch_log_group_api" {
  description = "CloudWatch log group for API service"
  value       = aws_cloudwatch_log_group.api.name
}

output "cloudwatch_log_group_mlflow" {
  description = "CloudWatch log group for MLflow service"
  value       = aws_cloudwatch_log_group.mlflow.name
}

output "api_ecr_repository_url" {
  description = "ECR repository URL for API service"
  value       = aws_ecr_repository.api.repository_url
}

output "mlflow_ecr_repository_url" {
  description = "ECR repository URL for MLflow service"
  value       = aws_ecr_repository.mlflow.repository_url
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = aws_lb.main.arn
}