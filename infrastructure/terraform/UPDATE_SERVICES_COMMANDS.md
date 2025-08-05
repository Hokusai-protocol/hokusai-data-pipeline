# ECS Service Update Commands

## Direct AWS CLI Commands to Update Services

These commands will update the ECS services to use the centralized infrastructure target groups.

### 1. Update API Service

```bash
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-api \
  --task-definition hokusai-api-development:58 \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81,containerName=hokusai-api,containerPort=8001 \
  --force-new-deployment
```

### 2. Update MLflow Service

```bash
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-mlflow \
  --task-definition hokusai-mlflow-development:29 \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-tg-development/9518cac0d6af96bb,containerName=hokusai-mlflow,containerPort=5000 \
  --force-new-deployment
```

### 3. Monitor Deployment Progress

```bash
# Watch the deployment status
watch -n 5 'aws ecs describe-services --cluster hokusai-development --services hokusai-api hokusai-mlflow --query "services[*].[serviceName,deployments[0].status,deployments[0].desiredCount,deployments[0].runningCount]" --output table'
```

### 4. Check Target Group Health

After the services are updated (5-10 minutes), check if the targets are healthy:

```bash
# Check API target group
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81

# Check MLflow target group
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-tg-development/9518cac0d6af96bb
```

## Important Notes

1. The update process will cause a rolling deployment where new tasks are started with the new target group before old tasks are stopped.
2. There should be minimal downtime as ECS handles the deployment gracefully.
3. The task definition versions may need to be updated - check current versions with:
   ```bash
   aws ecs describe-services --cluster hokusai-development --services hokusai-api hokusai-mlflow --query 'services[*].[serviceName,taskDefinition]' --output table
   ```

## Rollback

If needed, you can rollback by updating the services back to the original target groups:

```bash
# Rollback API service
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-api \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-ded2-dev/be83552b6df43d52,containerName=hokusai-api,containerPort=8001 \
  --force-new-deployment

# Rollback MLflow service  
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-mlflow \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-ded2-dev/3ba78fec193597df,containerName=hokusai-mlflow,containerPort=5000 \
  --force-new-deployment
```