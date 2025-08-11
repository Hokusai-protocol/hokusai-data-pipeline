# Redis Queue Integration Deployment Status

## Current Deployment State

**Date**: August 11, 2025  
**Status**: ⚠️ Partially Deployed

### What's Working ✅
- Redis integration code merged to main branch
- API service is running and healthy
- Health endpoint accessible at https://registry.hokus.ai/health
- Database (PostgreSQL) connection working
- MLflow integration functional

### What's Not Working ❌
- Redis connection failing (trying to connect to localhost:6379)
- Message queue shows as "unhealthy"
- Redis environment variables not being read correctly

## Root Cause

The ECS task definition references SSM parameters that don't exist:
- `/hokusai/development/redis/endpoint` - NOT FOUND
- `/hokusai/development/redis/port` - NOT FOUND

The application can't read these values and falls back to default localhost:6379.

## Solution Required

The infrastructure team needs to either:

### Option 1: Create SSM Parameters
```bash
aws ssm put-parameter \
  --name /hokusai/development/redis/endpoint \
  --value "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com" \
  --type String \
  --region us-east-1

aws ssm put-parameter \
  --name /hokusai/development/redis/port \
  --value "6379" \
  --type String \
  --region us-east-1
```

### Option 2: Update Task Definition
Use direct environment variables instead of SSM parameters:
```json
{
  "environment": [
    {
      "name": "REDIS_HOST",
      "value": "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com"
    },
    {
      "name": "REDIS_PORT",
      "value": "6379"
    }
  ]
}
```

## Testing After Fix

Once the environment variables are properly configured:

1. **Verify Redis Connection**:
```bash
curl https://registry.hokus.ai/health | jq '.services.redis'
# Should return: "healthy"
```

2. **Test Model Registration**:
```python
# Register a test model and verify message is published
python scripts/test_model_registration.py
```

3. **Check Queue Depth**:
```bash
# Monitor Redis queue for messages
python scripts/monitor_redis_queue.py
```

4. **Verify Logs**:
```bash
aws logs tail /ecs/hokusai-api-development --follow | grep -i redis
# Should see: "Connected to Redis at redis://..."
```

## Contact for Infrastructure Support

If you need help with the infrastructure configuration:
- Check `../hokusai-infrastructure` repository
- The task definitions are managed there
- SSM parameters need to be created in the infrastructure terraform

## Temporary Workaround

For immediate testing, you can:
1. Run the service locally with proper environment variables
2. Use docker-compose with Redis configuration
3. Test the queue integration in development environment

## Files Updated in This Deployment

- `.env.example` - Added Redis configuration variables
- `docker-compose.yml` - Updated for ElastiCache support
- `src/api/utils/config.py` - Added Redis configuration
- `src/events/publishers/factory.py` - Authentication support
- `src/api/routes/health.py` - Redis health checks
- `README.md` - Documentation updates

## Next Actions

1. **Infrastructure Team**: Create missing SSM parameters or update task definition
2. **After Fix**: Force new deployment of ECS service
3. **Validation**: Run integration tests to verify queue functionality
4. **Monitoring**: Set up CloudWatch alerts for queue depth

## Success Criteria

The deployment will be considered successful when:
- [ ] Health endpoint shows `"redis": "healthy"`
- [ ] Messages are published to Redis queue on model registration
- [ ] No Redis connection errors in logs
- [ ] Downstream services can consume messages from queue