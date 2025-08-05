# Migration Blocker - Action Required

## Issue Identified

The centralized target groups are not yet attached to any load balancers. The ECS services cannot be updated until the listener rules are created.

### Current Status

1. **Centralized Target Groups** ✅ Created
   - `hokusai-api-tg-development` - Created but not attached to ALB
   - `hokusai-mlflow-tg-development` - Created but not attached to ALB

2. **ECS Services** ✅ Running
   - Currently using old target groups that ARE attached to load balancers
   - Cannot switch to centralized target groups until they have load balancer associations

3. **Listener Rules** ❌ Not Created
   - Need to be enabled in centralized infrastructure repository
   - This will attach the target groups to the appropriate ALBs

## Required Actions (In Order)

### 1. Infrastructure Team Must Enable Listener Rules FIRST

The infrastructure team needs to:

1. Go to the `hokusai-infrastructure` repository
2. Rename `environments/data-pipeline-ecs-alb-integration.tf.disabled` to `environments/data-pipeline-ecs-alb-integration.tf`
3. Run `terraform apply` to create the listener rules

This will:
- Attach the API target group to the Main ALB
- Attach the MLflow target group to the Data Pipeline ALB
- Create the routing rules for `/api/*` and `/mlflow/*` paths

### 2. Verify Target Groups Have Load Balancers

After infrastructure team completes step 1, verify:

```bash
# Check API target group
aws elbv2 describe-target-groups \
  --target-group-arns arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81 \
  --query 'TargetGroups[*].[TargetGroupName,LoadBalancerArns]'

# Check MLflow target group  
aws elbv2 describe-target-groups \
  --target-group-arns arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-tg-development/9518cac0d6af96bb \
  --query 'TargetGroups[*].[TargetGroupName,LoadBalancerArns]'
```

The LoadBalancerArns should NOT be empty arrays.

### 3. Then Update ECS Services

Only after the target groups are attached to load balancers, run:

```bash
# Update API service
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-api \
  --task-definition hokusai-api-development:50 \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81,containerName=hokusai-api,containerPort=8001 \
  --force-new-deployment

# Update MLflow service
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-mlflow \
  --task-definition hokusai-mlflow-development:1 \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-tg-development/9518cac0d6af96bb,containerName=hokusai-mlflow,containerPort=5000 \
  --force-new-deployment
```

## Communication to Infrastructure Team

Please share this with the infrastructure team:

> The data pipeline ECS services are ready for migration, but we cannot proceed until the listener rules are enabled in the centralized infrastructure. The target groups have been created but need to be attached to the load balancers via listener rules. Please enable the file `environments/data-pipeline-ecs-alb-integration.tf.disabled` and apply the changes. Once complete, we can update our ECS services to use the centralized target groups.

## Files Ready for Infrastructure Team

The file `listener-rules-for-infra-team.tf.example` contains the complete listener rule configuration that should replace the disabled file in the centralized repository.

## Next Steps

1. ⏸️ **Wait** for infrastructure team to enable listener rules
2. ✅ **Verify** target groups are attached to load balancers
3. ▶️ **Run** the ECS service update commands
4. 🧪 **Test** the endpoints through centralized ALBs