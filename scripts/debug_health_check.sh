#!/bin/bash
# Debug health check issues

echo "=== Debugging Hokusai API Health Checks ==="
echo

# Get the running task
TASK_ARN=$(aws ecs list-tasks --cluster hokusai-development --service-name hokusai-api-development --desired-status RUNNING --query 'taskArns[0]' --output text)
echo "Task ARN: $TASK_ARN"

# Get task details
TASK_IP=$(aws ecs describe-tasks --cluster hokusai-development --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "Task IP: $TASK_IP"

# Get ENI ID
ENI_ID=$(aws ecs describe-tasks --cluster hokusai-development --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text)
echo "ENI ID: $ENI_ID"

# Get security groups from ENI
echo
echo "Security Groups on ENI:"
aws ec2 describe-network-interfaces --network-interface-ids $ENI_ID --query 'NetworkInterfaces[0].Groups[*].[GroupId,GroupName]' --output table

# Check if we can reach the health endpoint from the same subnet
echo
echo "Testing direct access to health endpoint..."
# This would require an EC2 instance in the same VPC

# Check container logs for any errors
echo
echo "Recent container logs:"
aws logs tail /ecs/hokusai-api-development --since 5m --format short | tail -10

# Check health check configuration
echo
echo "Target Group Health Check Config:"
aws elbv2 describe-target-groups --target-group-arns arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81 --query 'TargetGroups[0].[HealthCheckPath,HealthCheckPort,HealthCheckProtocol,HealthCheckIntervalSeconds,HealthyThresholdCount,UnhealthyThresholdCount]' --output table

# Check for failed health checks
echo
echo "Target Health Details:"
aws elbv2 describe-target-health --target-group-arn arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81 --targets Id=$TASK_IP,Port=8001 --query 'TargetHealthDescriptions[0].[TargetHealth.State,TargetHealth.Reason,TargetHealth.Description]' --output table