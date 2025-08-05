# Remote state data source for centralized infrastructure
data "terraform_remote_state" "infra" {
  backend = "s3"
  config = {
    bucket = "hokusai-infrastructure-tfstate"
    key    = "environments/development/terraform.tfstate"
    region = "us-east-1"
  }
}

# Local variables for infrastructure resources
locals {
  # ALB ARNs from centralized infrastructure
  main_alb_arn     = data.terraform_remote_state.infra.outputs.main_alb_arn
  dp_alb_arn       = data.terraform_remote_state.infra.outputs.data_pipeline_alb_arn
  registry_alb_arn = data.terraform_remote_state.infra.outputs.registry_alb_arn
  
  # Target Group ARNs from centralized infrastructure
  api_tg_arn      = data.terraform_remote_state.infra.outputs.api_target_group_arn
  mlflow_tg_arn   = data.terraform_remote_state.infra.outputs.mlflow_target_group_arn
  auth_tg_arn     = data.terraform_remote_state.infra.outputs.auth_target_group_arn
  reg_api_tg_arn  = data.terraform_remote_state.infra.outputs.registry_api_target_group_arn
  reg_mlflow_tg_arn = data.terraform_remote_state.infra.outputs.registry_mlflow_target_group_arn
  
  # Security Group IDs
  main_alb_sg_id = data.terraform_remote_state.infra.outputs.main_alb_security_group_id
  dp_alb_sg_id   = data.terraform_remote_state.infra.outputs.data_pipeline_alb_security_group_id
  registry_alb_sg_id = data.terraform_remote_state.infra.outputs.registry_alb_security_group_id
  
  # IAM Role ARNs
  ecs_execution_role_arn = data.terraform_remote_state.infra.outputs.ecs_task_execution_role_arn
  ecs_task_role_arn      = data.terraform_remote_state.infra.outputs.ecs_task_role_arn
}