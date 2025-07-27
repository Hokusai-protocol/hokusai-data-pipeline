# Message Queue Infrastructure Requirements

## Executive Summary

This document analyzes Redis vs AWS SQS for implementing the `model_ready_to_deploy` message queue feature in the Hokusai ML platform.

**Recommendation: Use Redis** - It's already deployed in our infrastructure and provides the required functionality with minimal additional overhead.

## Requirements

1. Emit messages when models pass baseline validation
2. Include metadata: model_id, token_symbol, metric, baseline value
3. Handle failures gracefully with retry logic
4. Support 99.9% message delivery reliability
5. Enable future scaling to multiple consumers

## Comparison Matrix

| Feature | Redis | AWS SQS |
|---------|-------|---------|
| **Already in Infrastructure** | ✅ Yes (docker-compose.yml) | ❌ No |
| **Setup Complexity** | ✅ None (already running) | ⚠️ Requires AWS configuration |
| **Cost** | ✅ Free (self-hosted) | 💰 Pay per message |
| **Message Persistence** | ✅ Configurable (AOF/RDB) | ✅ Built-in |
| **Retry Logic** | ⚠️ Manual implementation | ✅ Built-in DLQ |
| **Pub/Sub Support** | ✅ Native | ⚠️ Via SNS integration |
| **Monitoring** | ✅ Prometheus metrics | ✅ CloudWatch |
| **Local Development** | ✅ Easy | ⚠️ Requires LocalStack |
| **Message Ordering** | ✅ FIFO via lists | ✅ FIFO queues |
| **At-least-once Delivery** | ✅ With RPOPLPUSH | ✅ Built-in |

## Redis Implementation Details

### Advantages
- Zero additional infrastructure cost
- Already integrated with our stack
- Simple pub/sub for real-time notifications
- Reliable queue pattern with RPOPLPUSH
- Easy local development and testing

### Implementation Pattern
```python
# Reliable queue pattern
# 1. Push to main queue
redis.lpush("hokusai:model_ready_queue", message)

# 2. Consumer uses RPOPLPUSH for reliability
message = redis.rpoplpush("hokusai:model_ready_queue", "hokusai:processing")

# 3. After successful processing
redis.lrem("hokusai:processing", 1, message)

# 4. Failed messages can be requeued from processing list
```

### Configuration Requirements
```yaml
# Redis persistence configuration (redis.conf)
appendonly yes                    # Enable AOF for durability
appendfsync everysec              # Balance performance/durability
save 900 1                        # RDB snapshots
save 300 10
save 60 10000
```

## AWS SQS Alternative

### When to Consider SQS
- If message volume exceeds 100k/day
- If we need cross-region replication
- If we require guaranteed exactly-once processing
- If we move to serverless architecture

### Implementation Complexity
- Requires AWS credentials management
- Needs IAM role configuration
- Additional terraform resources
- LocalStack for local development

## Recommendation

**Use Redis** for the initial implementation because:

1. **No Additional Infrastructure**: Redis is already running in our stack
2. **Proven Reliability**: Redis pub/sub and lists are battle-tested
3. **Simple Implementation**: Well-documented patterns exist
4. **Easy Migration Path**: Can add SQS later if needed
5. **Cost Effective**: No additional AWS costs

## Implementation Plan

1. Use Redis LIST for reliable queue
2. Implement retry with exponential backoff
3. Add dead letter queue as separate LIST
4. Monitor queue depth via Prometheus
5. Document migration path to SQS if needed

## Infrastructure PR Requirements

No infrastructure changes needed for Redis implementation. The existing Redis service in docker-compose.yml is sufficient.

For future SQS migration, we would need:
- SQS queue terraform resource
- IAM role for ECS tasks
- Dead letter queue configuration
- CloudWatch alarms