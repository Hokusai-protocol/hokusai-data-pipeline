# Product Requirements Document: Replace Redis Pub/Sub with Webhook System

## Objectives

Replace the current Redis pub/sub notification system with an HTTP webhook mechanism for model registration events. This change enables Vercel and other serverless platforms to receive model registration notifications without requiring persistent Redis consumers.

## Success Criteria

1. Model registration events trigger HTTP POST requests to configured webhook endpoints
2. Webhook delivery includes retry logic with exponential backoff for reliability
3. Payload security via HMAC signature verification
4. Zero downtime migration with temporary dual publishing support
5. All existing event data preserved in webhook payloads
6. Comprehensive error handling and monitoring

## Technical Requirements

### Webhook Publisher Implementation

Create a new WebhookPublisher class that implements the BasePublisher interface with the following capabilities:
- HTTP POST requests to configured webhook URLs
- Configurable retry mechanism with exponential backoff
- Circuit breaker pattern for endpoint health management
- Request timeout handling
- Connection pooling for performance

### Message Payload Structure

Webhook payloads must include:
- model_id: Unique identifier for the registered model
- idempotency_key: UUID or hash for duplicate prevention
- registered_version: Model version number
- timestamp: ISO 8601 formatted registration time
- token_symbol: Associated token identifier
- baseline_metrics: Performance baseline data
- metadata: Additional model metadata

### Security Implementation

- HMAC-SHA256 signature generation using shared secret
- Signature included in X-Hokusai-Signature header
- Timestamp validation to prevent replay attacks
- HTTPS-only webhook endpoints requirement
- Secret rotation support without downtime

### Configuration Management

Environment variables for webhook configuration:
- WEBHOOK_URL: Primary webhook endpoint
- WEBHOOK_SECRET: Shared secret for HMAC signing
- WEBHOOK_TIMEOUT: Request timeout in seconds
- WEBHOOK_MAX_RETRIES: Maximum retry attempts
- WEBHOOK_RETRY_DELAY: Initial retry delay in seconds
- ENABLE_REDIS_FALLBACK: Toggle for migration period

### Reliability Features

- Retry logic with exponential backoff (2, 4, 8, 16, 32 seconds)
- Circuit breaker with configurable thresholds
- Dead letter queue for failed webhook deliveries
- Health check endpoint for webhook status monitoring
- Metrics collection for delivery success/failure rates

### Migration Strategy

Phase 1: Dual Publishing
- Deploy webhook publisher alongside Redis publisher
- Both systems publish simultaneously
- Monitor webhook delivery success rates

Phase 2: Webhook Primary
- Make webhook publisher primary notification method
- Keep Redis as fallback for critical failures
- Begin deprecation notices for Redis consumers

Phase 3: Redis Removal
- Remove Redis publisher code
- Clean up Redis configuration
- Archive Redis consumer documentation

## Implementation Tasks

### Core Development

1. Implement WebhookPublisher class extending BasePublisher
2. Add HTTP client with connection pooling
3. Implement HMAC signature generation
4. Create retry mechanism with exponential backoff
5. Add circuit breaker for endpoint health
6. Implement idempotency handling

### Integration Points

1. Update publisher factory to support webhook publisher
2. Modify model registry hooks to use webhook publisher
3. Add webhook configuration to settings
4. Update environment variable templates
5. Create webhook health check endpoint

### Testing Requirements

1. Unit tests for WebhookPublisher class
2. Integration tests for end-to-end webhook delivery
3. Security tests for HMAC signature validation
4. Reliability tests for retry and circuit breaker
5. Performance tests for high-volume scenarios
6. Migration tests for dual publishing mode

### Documentation Updates

1. Update API documentation with webhook specifications
2. Create webhook integration guide for consumers
3. Document HMAC signature verification process
4. Add troubleshooting guide for webhook issues
5. Update deployment documentation

### Monitoring and Observability

1. Add CloudWatch metrics for webhook delivery
2. Create dashboard for webhook health monitoring
3. Set up alerts for delivery failures
4. Implement structured logging for debugging
5. Add distributed tracing support

## Rollback Plan

If webhook implementation encounters critical issues:
1. Toggle ENABLE_REDIS_FALLBACK to revert to Redis
2. No code deployment required for rollback
3. Monitor Redis queue to ensure message delivery
4. Investigate webhook issues offline
5. Re-attempt migration after fixes