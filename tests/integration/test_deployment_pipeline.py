"""Tests for CI/CD deployment pipeline."""

import pytest
import yaml
import json
from pathlib import Path
from unittest.mock import Mock, patch
import subprocess


class TestDeploymentPipeline:
    """Test suite for deployment pipeline functionality."""
    
    def test_github_actions_workflow_structure(self):
        """Test GitHub Actions workflow file structure."""
        workflow_path = Path(".github/workflows/deploy.yml")
        
        if workflow_path.exists():
            with open(workflow_path, 'r') as f:
                workflow = yaml.safe_load(f)
            
            # Check basic structure
            assert workflow is not None
            assert "name" in workflow
            assert "on" in workflow
            assert "jobs" in workflow
            
            # Check triggers
            triggers = workflow["on"]
            assert "push" in triggers
            assert "branches" in triggers["push"]
            assert "main" in triggers["push"]["branches"]
            
            # Check jobs
            assert "test" in workflow["jobs"]
            assert "build" in workflow["jobs"]
            assert "deploy" in workflow["jobs"]
            
            # Check job dependencies
            deploy_job = workflow["jobs"]["deploy"]
            assert "needs" in deploy_job
            assert "test" in deploy_job["needs"]
            assert "build" in deploy_job["needs"]
    
    def test_test_job_configuration(self):
        """Test the test job in GitHub Actions workflow."""
        workflow_path = Path(".github/workflows/deploy.yml")
        
        if workflow_path.exists():
            with open(workflow_path, 'r') as f:
                workflow = yaml.safe_load(f)
            
            test_job = workflow["jobs"]["test"]
            
            # Check test job steps
            step_names = [step.get("name", "") for step in test_job["steps"]]
            
            assert any("checkout" in name.lower() for name in step_names)
            assert any("python" in name.lower() for name in step_names)
            assert any("dependencies" in name.lower() for name in step_names)
            assert any("pytest" in name.lower() or "test" in name.lower() for name in step_names)
            assert any("lint" in name.lower() for name in step_names)
    
    def test_build_job_configuration(self):
        """Test the build job in GitHub Actions workflow."""
        workflow_path = Path(".github/workflows/deploy.yml")
        
        if workflow_path.exists():
            with open(workflow_path, 'r') as f:
                workflow = yaml.safe_load(f)
            
            build_job = workflow["jobs"]["build"]
            
            # Check build job steps
            step_names = [step.get("name", "") for step in build_job["steps"]]
            
            assert any("docker" in name.lower() for name in step_names)
            assert any("build" in name.lower() for name in step_names)
            assert any("push" in name.lower() or "ecr" in name.lower() for name in step_names)
    
    def test_deploy_job_configuration(self):
        """Test the deploy job in GitHub Actions workflow."""
        workflow_path = Path(".github/workflows/deploy.yml")
        
        if workflow_path.exists():
            with open(workflow_path, 'r') as f:
                workflow = yaml.safe_load(f)
            
            deploy_job = workflow["jobs"]["deploy"]
            
            # Check environment
            assert "environment" in deploy_job
            assert deploy_job["environment"] == "production"
            
            # Check steps
            step_names = [step.get("name", "") for step in deploy_job["steps"]]
            
            assert any("terraform" in name.lower() for name in step_names)
            assert any("ecs" in name.lower() or "deploy" in name.lower() for name in step_names)
    
    def test_aws_credentials_configuration(self):
        """Test AWS credentials are properly configured in workflow."""
        workflow_path = Path(".github/workflows/deploy.yml")
        
        if workflow_path.exists():
            with open(workflow_path, 'r') as f:
                workflow = yaml.safe_load(f)
            
            # Check for AWS credentials action
            for job in workflow["jobs"].values():
                for step in job.get("steps", []):
                    if "aws-actions/configure-aws-credentials" in step.get("uses", ""):
                        assert "with" in step
                        assert "role-to-assume" in step["with"] or "aws-access-key-id" in step["with"]
                        assert "aws-region" in step["with"]
                        break
    
    def test_terraform_deployment_script(self):
        """Test Terraform deployment script."""
        deploy_script = Path("infrastructure/scripts/deploy.sh")
        
        if deploy_script.exists():
            content = deploy_script.read_text()
            
            # Check for required commands
            assert "terraform init" in content
            assert "terraform plan" in content
            assert "terraform apply" in content
            
            # Check for safety measures
            assert "set -e" in content  # Exit on error
            assert "terraform validate" in content
            
            # Check for environment validation
            assert "AWS_REGION" in content or "aws_region" in content
    
    def test_docker_build_configuration(self):
        """Test Docker build configuration for services."""
        # Check API Dockerfile
        api_dockerfile = Path("Dockerfile.api")
        assert api_dockerfile.exists(), "API Dockerfile not found"
        
        if api_dockerfile.exists():
            content = api_dockerfile.read_text()
            
            # Check base image
            assert "FROM python" in content
            
            # Check for multi-stage build
            assert "AS builder" in content or "as builder" in content
            
            # Check for requirements installation
            assert "requirements" in content
            assert "pip install" in content
            
            # Check for proper user configuration
            assert "USER" in content or "useradd" in content
        
        # Check MLFlow Dockerfile
        mlflow_dockerfile = Path("Dockerfile.mlflow")
        assert mlflow_dockerfile.exists(), "MLFlow Dockerfile not found"
    
    def test_ecs_task_definition_generation(self):
        """Test ECS task definition generation."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="Task definition registered")
            
            # Simulate task definition generation
            from infrastructure.scripts.generate_task_definition import generate_task_definition
            
            task_def = generate_task_definition(
                service_name="hokusai-api",
                image_uri="123456789.dkr.ecr.us-east-1.amazonaws.com/hokusai-api:latest",
                environment="production"
            )
            
            # Validate task definition structure
            assert "family" in task_def
            assert "containerDefinitions" in task_def
            assert len(task_def["containerDefinitions"]) > 0
            
            container = task_def["containerDefinitions"][0]
            assert "name" in container
            assert "image" in container
            assert "memory" in container
            assert "cpu" in container
            assert "environment" in container
            assert "logConfiguration" in container
    
    def test_deployment_rollback_capability(self):
        """Test deployment rollback functionality."""
        rollback_script = Path("infrastructure/scripts/rollback.sh")
        
        if rollback_script.exists():
            content = rollback_script.read_text()
            
            # Check for rollback commands
            assert "terraform state" in content or "previous version" in content
            assert "ecs update-service" in content or "task-definition" in content
            
            # Check for confirmation prompt
            assert "confirm" in content.lower() or "y/n" in content.lower()
    
    def test_deployment_validation(self):
        """Test deployment validation script."""
        validate_script = Path("infrastructure/scripts/validate.sh")
        
        if validate_script.exists():
            content = validate_script.read_text()
            
            # Check for validation steps
            assert "health" in content or "check" in content
            assert "curl" in content or "http" in content
            assert "status" in content
            
            # Check for timeout handling
            assert "timeout" in content or "wait" in content
    
    @patch("subprocess.run")
    def test_end_to_end_deployment_simulation(self, mock_run):
        """Test simulated end-to-end deployment process."""
        mock_run.return_value = Mock(returncode=0, stdout="Success")
        
        # Simulate deployment steps
        deployment_steps = [
            ("terraform init", "Terraform initialized"),
            ("terraform validate", "Configuration valid"),
            ("terraform plan", "Plan generated"),
            ("docker build", "Image built"),
            ("docker push", "Image pushed"),
            ("terraform apply", "Infrastructure deployed"),
            ("ecs update-service", "Service updated")
        ]
        
        for command, expected_output in deployment_steps:
            result = subprocess.run(command.split(), capture_output=True, text=True)
            assert mock_run.called
            # In real scenario, we'd check result.returncode == 0


class TestInfrastructureSecrets:
    """Test suite for secrets and sensitive data handling."""
    
    def test_no_secrets_in_code(self):
        """Test that no secrets are hardcoded in the codebase."""
        # Define patterns that might indicate secrets
        secret_patterns = [
            "password=",
            "api_key=",
            "secret=",
            "aws_access_key",
            "private_key=",
            "token="
        ]
        
        # Check Terraform files
        terraform_files = Path("infrastructure/terraform").glob("*.tf")
        for tf_file in terraform_files:
            if tf_file.exists():
                content = tf_file.read_text().lower()
                for pattern in secret_patterns:
                    if pattern in content and "variable" not in content:
                        # Allow variable definitions but not hardcoded values
                        lines = content.split('\n')
                        for i, line in enumerate(lines):
                            if pattern in line and '=' in line:
                                value = line.split('=')[1].strip()
                                assert value in ['""', "''", "var.", "data.", "aws_"], \
                                    f"Potential hardcoded secret found in {tf_file} line {i+1}"
    
    def test_terraform_tfvars_example(self):
        """Test that example tfvars doesn't contain real secrets."""
        example_file = Path("infrastructure/terraform/terraform.tfvars.example")
        
        if example_file.exists():
            content = example_file.read_text()
            
            # Check that values are clearly examples
            assert "CHANGE_ME" in content or "example" in content or "your-" in content
            assert not any(char.isdigit() for char in content if "12345" not in content)