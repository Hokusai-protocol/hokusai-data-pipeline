"""Tests for infrastructure configuration validation."""

import pytest
import json
import yaml
from pathlib import Path
from typing import Dict, Any


class TestInfrastructureValidation:
    """Test suite for validating infrastructure configuration."""
    
    def test_terraform_files_exist(self):
        """Test that required Terraform files exist."""
        terraform_dir = Path("infrastructure/terraform")
        
        required_files = [
            "main.tf",
            "variables.tf", 
            "outputs.tf",
            "terraform.tfvars.example"
        ]
        
        for file_name in required_files:
            file_path = terraform_dir / file_name
            assert file_path.exists(), f"Required Terraform file {file_name} not found"
    
    def test_terraform_provider_configuration(self):
        """Test that AWS provider is properly configured."""
        main_tf = Path("infrastructure/terraform/main.tf")
        
        if main_tf.exists():
            content = main_tf.read_text()
            assert "provider \"aws\"" in content, "AWS provider not configured"
            assert "region" in content, "AWS region not specified"
    
    def test_s3_bucket_configuration(self):
        """Test S3 bucket configurations are present."""
        main_tf = Path("infrastructure/terraform/main.tf")
        
        if main_tf.exists():
            content = main_tf.read_text()
            
            # Check for MLFlow artifacts bucket
            assert "hokusai-mlflow-artifacts" in content or "mlflow_artifacts_bucket" in content, \
                "MLFlow artifacts bucket not configured"
            
            # Check for pipeline data bucket  
            assert "hokusai-pipeline-data" in content or "pipeline_data_bucket" in content, \
                "Pipeline data bucket not configured"
            
            # Check for versioning and encryption
            assert "versioning" in content, "S3 versioning not configured"
            assert "server_side_encryption" in content or "encryption" in content, \
                "S3 encryption not configured"
    
    def test_rds_configuration(self):
        """Test RDS PostgreSQL configuration."""
        main_tf = Path("infrastructure/terraform/main.tf")
        
        if main_tf.exists():
            content = main_tf.read_text()
            
            # Check for RDS instance
            assert "aws_db_instance" in content, "RDS instance not configured"
            assert "postgres" in content.lower(), "PostgreSQL engine not specified"
            assert "multi_az" in content, "Multi-AZ not configured"
            assert "backup_retention_period" in content, "Backup retention not configured"
    
    def test_vpc_configuration(self):
        """Test VPC and networking configuration."""
        main_tf = Path("infrastructure/terraform/main.tf")
        
        if main_tf.exists():
            content = main_tf.read_text()
            
            # Check for VPC resources
            assert "aws_vpc" in content, "VPC not configured"
            assert "aws_subnet" in content, "Subnets not configured"
            assert "aws_internet_gateway" in content, "Internet gateway not configured"
            assert "aws_nat_gateway" in content, "NAT gateway not configured"
            assert "aws_security_group" in content, "Security groups not configured"
    
    def test_ecs_configuration(self):
        """Test ECS cluster and service configuration."""
        main_tf = Path("infrastructure/terraform/main.tf")
        
        if main_tf.exists():
            content = main_tf.read_text()
            
            # Check for ECS resources
            assert "aws_ecs_cluster" in content, "ECS cluster not configured"
            assert "aws_ecs_task_definition" in content, "Task definitions not configured"
            assert "aws_ecs_service" in content, "ECS services not configured"
    
    def test_alb_configuration(self):
        """Test Application Load Balancer configuration."""
        main_tf = Path("infrastructure/terraform/main.tf")
        
        if main_tf.exists():
            content = main_tf.read_text()
            
            # Check for ALB resources
            assert "aws_lb" in content or "aws_alb" in content, "Load balancer not configured"
            assert "aws_lb_target_group" in content or "aws_alb_target_group" in content, \
                "Target groups not configured"
            assert "health_check" in content, "Health checks not configured"
    
    def test_iam_roles_configuration(self):
        """Test IAM roles and policies configuration."""
        main_tf = Path("infrastructure/terraform/main.tf")
        
        if main_tf.exists():
            content = main_tf.read_text()
            
            # Check for IAM resources
            assert "aws_iam_role" in content, "IAM roles not configured"
            assert "aws_iam_policy" in content or "aws_iam_role_policy" in content, \
                "IAM policies not configured"
    
    def test_cloudwatch_configuration(self):
        """Test CloudWatch monitoring configuration."""
        main_tf = Path("infrastructure/terraform/main.tf")
        
        if main_tf.exists():
            content = main_tf.read_text()
            
            # Check for CloudWatch resources
            assert "aws_cloudwatch_log_group" in content, "CloudWatch log groups not configured"
            assert "aws_cloudwatch_metric_alarm" in content, "CloudWatch alarms not configured"
    
    def test_secrets_manager_configuration(self):
        """Test AWS Secrets Manager configuration."""
        main_tf = Path("infrastructure/terraform/main.tf")
        
        if main_tf.exists():
            content = main_tf.read_text()
            
            # Check for Secrets Manager resources
            assert "aws_secretsmanager_secret" in content, "Secrets Manager not configured"
    
    def test_terraform_variables(self):
        """Test that all required variables are defined."""
        variables_tf = Path("infrastructure/terraform/variables.tf")
        
        if variables_tf.exists():
            content = variables_tf.read_text()
            
            required_vars = [
                "aws_region",
                "environment",
                "project_name",
                "vpc_cidr",
                "database_password",
                "api_secret_key"
            ]
            
            for var in required_vars:
                assert f"variable \"{var}\"" in content, f"Required variable {var} not defined"
    
    def test_terraform_outputs(self):
        """Test that necessary outputs are defined."""
        outputs_tf = Path("infrastructure/terraform/outputs.tf")
        
        if outputs_tf.exists():
            content = outputs_tf.read_text()
            
            required_outputs = [
                "api_endpoint",
                "mlflow_endpoint",
                "s3_artifacts_bucket",
                "database_endpoint"
            ]
            
            for output in required_outputs:
                assert f"output \"{output}\"" in content, f"Required output {output} not defined"
    
    def test_terraform_example_vars(self):
        """Test that example variables file exists and is valid."""
        example_file = Path("infrastructure/terraform/terraform.tfvars.example")
        
        assert example_file.exists(), "terraform.tfvars.example file not found"
        
        if example_file.exists():
            content = example_file.read_text()
            
            # Check for example values
            assert "aws_region" in content, "Example AWS region not provided"
            assert "environment" in content, "Example environment not provided"
            assert "project_name" in content, "Example project name not provided"


class TestDeploymentScripts:
    """Test suite for deployment scripts."""
    
    def test_deployment_scripts_exist(self):
        """Test that required deployment scripts exist."""
        scripts_dir = Path("infrastructure/scripts")
        
        required_scripts = [
            "deploy.sh",
            "validate.sh",
            "destroy.sh"
        ]
        
        for script_name in required_scripts:
            script_path = scripts_dir / script_name
            assert script_path.exists(), f"Required script {script_name} not found"
            
            if script_path.exists():
                # Check if script is executable
                assert script_path.stat().st_mode & 0o111, f"Script {script_name} is not executable"
    
    def test_github_actions_workflow(self):
        """Test GitHub Actions deployment workflow."""
        workflow_file = Path(".github/workflows/deploy.yml")
        
        assert workflow_file.exists(), "GitHub Actions deployment workflow not found"
        
        if workflow_file.exists():
            with open(workflow_file, 'r') as f:
                workflow = yaml.safe_load(f)
            
            # Check workflow structure
            assert "name" in workflow, "Workflow name not defined"
            assert "on" in workflow, "Workflow triggers not defined"
            assert "jobs" in workflow, "Workflow jobs not defined"
            
            # Check for deployment job
            assert "deploy" in workflow["jobs"], "Deploy job not defined"
            
            deploy_job = workflow["jobs"]["deploy"]
            assert "steps" in deploy_job, "Deploy job steps not defined"
            
            # Check for required steps
            step_names = [step.get("name", "") for step in deploy_job["steps"]]
            assert any("checkout" in name.lower() for name in step_names), "Checkout step not found"
            assert any("aws" in name.lower() for name in step_names), "AWS configuration step not found"
            assert any("terraform" in name.lower() for name in step_names), "Terraform step not found"
            assert any("docker" in name.lower() for name in step_names), "Docker build step not found"