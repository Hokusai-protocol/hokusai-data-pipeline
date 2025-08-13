# Product Requirements Document: Redis Connection Debugging and Resilience

## Objectives

Fix Redis connection issues in the hokusai-data-pipeline API service to ensure reliable message queue functionality and prevent service health check failures.

## Problem Statement

The API service is experiencing Redis connection failures that cause:
- Health check timeouts marking the entire service as unhealthy
- Inability to publish model registration events to the message queue
- Service attempting to connect to localhost:6379 instead of ElastiCache endpoint
- Missing SSM parameters that the ECS task definition expects

## Success Criteria

1. API service remains healthy even when Redis is temporarily unavailable
2. Redis connection properly uses ElastiCache endpoint from environment variables
3. Health checks complete within 5 seconds regardless of Redis status
4. Message queue publishes successfully when Redis is available
5. Service gracefully degrades when Redis is unavailable

## Technical Requirements

### Configuration Management
- Read Redis configuration from environment variables (REDIS_HOST, REDIS_PORT, REDIS_AUTH_TOKEN)
- Remove dependency on non-existent SSM parameters
- Implement proper fallback handling without defaulting to localhost

### Health Check Improvements
- Make Redis health check non-blocking
- Implement timeout protection for Redis operations
- Return degraded status instead of unhealthy when only Redis fails
- Add circuit breaker pattern to prevent repeated connection attempts

### Connection Resilience
- Implement connection pooling with proper timeout settings
- Add retry logic with exponential backoff
- Cache connection status to avoid repeated failed attempts
- Log detailed error messages for debugging

### Message Queue Handling
- Queue messages locally when Redis unavailable
- Implement fallback publisher that logs messages
- Add metrics for queue depth and failed publishes
- Ensure no data loss during Redis outages

## Implementation Tasks

### Phase 1: Immediate Fixes
1. Fix environment variable reading in configuration
2. Add connection timeout settings
3. Make health check non-blocking
4. Add proper error logging

### Phase 2: Resilience Improvements
1. Implement circuit breaker for Redis operations
2. Add local message buffering
3. Create fallback publisher
4. Add retry mechanisms

### Phase 3: Monitoring and Testing
1. Add CloudWatch metrics
2. Create integration tests
3. Document configuration requirements
4. Update deployment scripts

## Testing Requirements

### Unit Tests
- Redis connection with various configurations
- Health check behavior with/without Redis
- Message publishing with fallback scenarios
- Circuit breaker state transitions

### Integration Tests
- ElastiCache connection with authentication
- Health endpoint response times
- Message queue operations
- Service recovery after Redis restoration

### Load Tests
- Health check performance under load
- Message queue throughput
- Connection pool behavior
- Memory usage during Redis outages

## Rollback Strategy

1. Revert code changes if core API functionality affected
2. Restore previous ECS task definition
3. Monitor service health metrics
4. Document any configuration changes needed

## Dependencies

- Access to AWS ElastiCache Redis instance
- Environment variables properly configured in ECS
- CloudWatch metrics for monitoring
- Redis Python client library

## Timeline

- Phase 1: 2 hours (immediate fixes)
- Phase 2: 4 hours (resilience improvements)
- Phase 3: 2 hours (monitoring and testing)
- Total: 8 hours of development time