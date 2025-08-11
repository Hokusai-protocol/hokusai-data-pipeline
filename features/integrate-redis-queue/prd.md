# Product Requirements Document: Redis Queue Integration

## Objectives

Enable the Hokusai data pipeline to publish messages to the deployed Redis ElastiCache queue when models are successfully registered, allowing downstream services (hokusai-site and hokusai-token repos) to consume these events for token deployment and marketplace updates.

## Personas

**AI Developers**: Register models through the API and need confirmation that their models are queued for token deployment.

**Platform Services**: hokusai-site and hokusai-token services that consume model registration events to trigger token creation and marketplace listings.

**DevOps Engineers**: Monitor queue health, message throughput, and troubleshoot integration issues.

## Success Criteria

1. Model registration automatically publishes "model_ready_to_deploy" messages to Redis queue
2. Messages contain complete model metadata (model_id, token_symbol, metrics, baseline)
3. Queue maintains 99.9% availability with retry logic for transient failures
4. Health endpoints report Redis connectivity and queue depth metrics
5. Zero message loss with dead letter queue for failed messages
6. Authentication secured through AWS Secrets Manager integration

## Tasks

### Configuration Integration

Update environment configuration to connect to the deployed Redis ElastiCache cluster instead of local Redis. The system needs to authenticate using the token from AWS Secrets Manager and connect to the production endpoint.

### Authentication Implementation

Modify the Redis publisher to support ElastiCache authentication tokens. The current implementation uses unauthenticated connections suitable for local development but needs to handle auth tokens for the production ElastiCache cluster.

### Message Publishing Flow

Ensure the model registration workflow triggers Redis message publication after successful registration and baseline validation. The existing hook system should publish structured messages containing model metadata required for token deployment.

### Health Monitoring

Update health check endpoints to verify Redis ElastiCache connectivity and report queue depths. The monitoring should detect connection failures, authentication issues, and queue backlog problems.

### Environment Variable Management

Configure ECS task definitions with Redis connection parameters from SSM Parameter Store and Secrets Manager. Services need access to REDIS_HOST, REDIS_PORT, and REDIS_AUTH_TOKEN environment variables.

### Testing Infrastructure

Validate end-to-end message flow from model registration through Redis queue to consumer services. Tests should verify message format, retry logic, and error handling scenarios.

### Documentation Updates

Document the Redis integration configuration, message schemas, and troubleshooting procedures for operations teams. Include examples of consuming messages from the queue.

## Technical Requirements

**Redis Details**:
- Endpoint: master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com:6379
- Auth Token: Secrets Manager key hokusai/redis/development/auth-token-0GWWJx
- Multi-AZ deployment with encryption enabled

**Message Schema**:
- Event type: "model_ready_to_deploy"
- Payload: model_id, token_symbol, metric_name, baseline_value, performance_data
- Envelope: timestamp, retry_count, correlation_id

**Queue Structure**:
- Main queue: model_events
- Processing queue: model_events:processing
- Dead letter queue: model_events:dlq

**Performance Requirements**:
- Message publishing latency < 100ms
- Support 1000 messages/second throughput
- Automatic retry with exponential backoff
- Maximum 3 retry attempts before DLQ