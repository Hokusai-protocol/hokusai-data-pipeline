#!/bin/bash

# Fix Security Groups for Centralized ALB Access

echo "=== Fixing Security Groups for Health Checks ==="
echo

# Security Group IDs
MAIN_ALB_SG="sg-0009788bcb980224b"
ECS_TASK_SG="sg-0e61190afc2502b10"

echo "Adding ingress rule to allow traffic from Main ALB to ECS tasks..."

# Add ingress rule to ECS task security group to allow traffic from Main ALB
aws ec2 authorize-security-group-ingress \
  --group-id $ECS_TASK_SG \
  --protocol tcp \
  --port 1-65535 \
  --source-group $MAIN_ALB_SG \
  --group-owner-id 932100697590 \
  --tag-specifications "ResourceType=security-group-rule,Tags=[{Key=Name,Value=AllowFromMainALB},{Key=Purpose,Value=HealthChecks}]" \
  && echo "✅ Successfully added ingress rule" \
  || echo "❌ Failed to add ingress rule (may already exist)"

echo
echo "Current ingress rules for ECS task security group:"
aws ec2 describe-security-groups --group-ids $ECS_TASK_SG \
  --query 'SecurityGroups[0].IpPermissions[*].[IpProtocol,FromPort,ToPort,UserIdGroupPairs[0].GroupId]' \
  --output table

echo
echo "Waiting for health checks to stabilize..."
sleep 30

echo
echo "Checking target health:"
echo "API Target Group:"
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81 \
  --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State]' \
  --output table

echo
echo "MLflow Target Group:"
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-tg-development/9518cac0d6af96bb \
  --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State]' \
  --output table