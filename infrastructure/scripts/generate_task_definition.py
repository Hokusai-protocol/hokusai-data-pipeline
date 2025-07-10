#!/usr/bin/env python3
"""Generate ECS task definitions for Hokusai services."""

import json
import os
from typing import Any, Dict


def generate_task_definition(
    service_name: str,
    image_uri: str,
    environment: str,
    cpu: int = 256,
    memory: int = 512,
    port: int = 8001
) -> Dict[str, Any]:
    """Generate ECS task definition for a service."""

    # Environment variables for the container
    env_vars = [
        {"name": "ENVIRONMENT", "value": environment},
        {"name": "AWS_DEFAULT_REGION", "value": os.environ.get("AWS_REGION", "us-east-1")},
    ]

    # Service-specific configuration
    if service_name == "hokusai-api":
        env_vars.extend([
            {"name": "API_HOST", "value": "0.0.0.0"},
            {"name": "API_PORT", "value": str(port)},
            {"name": "MLFLOW_TRACKING_URI", "value": "http://hokusai-mlflow:5000"},
        ])
    elif service_name == "hokusai-mlflow":
        env_vars.extend([
            {"name": "MLFLOW_HOST", "value": "0.0.0.0"},
            {"name": "MLFLOW_PORT", "value": "5000"},
            {"name": "BACKEND_STORE_URI", "value": "postgresql://mlflow:${DATABASE_PASSWORD}@${DATABASE_ENDPOINT}/mlflow_db"},
            {"name": "DEFAULT_ARTIFACT_ROOT", "value": "s3://${S3_ARTIFACTS_BUCKET}/artifacts"},
        ])
        port = 5000

    # Generate task definition
    task_definition = {
        "family": f"{service_name}-{environment}",
        "networkMode": "awsvpc",
        "requiresCompatibilities": ["FARGATE"],
        "cpu": str(cpu),
        "memory": str(memory),
        "containerDefinitions": [
            {
                "name": service_name,
                "image": image_uri,
                "cpu": cpu,
                "memory": memory,
                "essential": True,
                "environment": env_vars,
                "portMappings": [
                    {
                        "containerPort": port,
                        "protocol": "tcp"
                    }
                ],
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": f"/ecs/hokusai/{service_name}/{environment}",
                        "awslogs-region": os.environ.get("AWS_REGION", "us-east-1"),
                        "awslogs-stream-prefix": "ecs"
                    }
                },
                "healthCheck": {
                    "command": [
                        "CMD-SHELL",
                        f"curl -f http://localhost:{port}/health || exit 1"
                    ],
                    "interval": 30,
                    "timeout": 5,
                    "retries": 3,
                    "startPeriod": 60
                }
            }
        ],
        "executionRoleArn": "${ECS_TASK_EXECUTION_ROLE_ARN}",
        "taskRoleArn": "${ECS_TASK_ROLE_ARN}"
    }

    # Add secrets from Secrets Manager
    if service_name == "hokusai-api":
        task_definition["containerDefinitions"][0]["secrets"] = [
            {
                "name": "SECRET_KEY",
                "valueFrom": "${APP_SECRETS_ARN}:secret_key::"
            },
            {
                "name": "DATABASE_PASSWORD",
                "valueFrom": "${APP_SECRETS_ARN}:database_password::"
            }
        ]

    return task_definition


def save_task_definition(task_def: Dict[str, Any], output_path: str) -> None:
    """Save task definition to file."""
    with open(output_path, "w") as f:
        json.dump(task_def, f, indent=2)
    print(f"Task definition saved to: {output_path}")


def main() -> None:
    """Generate task definitions for all services."""
    environment = os.environ.get("ENVIRONMENT", "development")

    # API service task definition
    api_task_def = generate_task_definition(
        service_name="hokusai-api",
        image_uri=os.environ.get("API_IMAGE_URI", "hokusai-api:latest"),
        environment=environment,
        cpu=int(os.environ.get("API_CPU", 256)),
        memory=int(os.environ.get("API_MEMORY", 512))
    )
    save_task_definition(api_task_def, f"task-def-api-{environment}.json")

    # MLflow service task definition
    mlflow_task_def = generate_task_definition(
        service_name="hokusai-mlflow",
        image_uri=os.environ.get("MLFLOW_IMAGE_URI", "hokusai-mlflow:latest"),
        environment=environment,
        cpu=int(os.environ.get("MLFLOW_CPU", 512)),
        memory=int(os.environ.get("MLFLOW_MEMORY", 1024))
    )
    save_task_definition(mlflow_task_def, f"task-def-mlflow-{environment}.json")


if __name__ == "__main__":
    # Make the module importable for tests
    pass
