# Codebase Knowledge Map
_Last updated: 2025-09-05_

## Components & Services

### ML Platform Core
- **ModelRegistry**: Central model registration and tracking system, integrates with MLflow API [details: hokusai-ml-platform/src/hokusai/core/registry.py]
- **ExperimentManager**: MLflow-based experiment tracking and versioning [details: hokusai-ml-platform/src/hokusai/tracking/]
- **MLFlow Service**: Tracking server for experiments and model registry, accessible at registry.hokus.ai [port: 5000/5001]
- **API Service**: REST API for model serving and inference at api.hokus.ai [port: 8001]

### Infrastructure Services
- **DNS Resolver**: DNS resolution with caching (5-min TTL), fallback to cached IPs, env variable override support [details: features/dns-resolution-fallback/prd.md]
- **Service Discovery**: ECS-based service discovery using hokusai-development.local namespace [details: CLAUDE.md]
- **Health Monitoring**: Comprehensive health checks with DNS resolution status tracking [details: src/api/routes/health.py]

## Documented Flows

### Model Registration Flow
- Train model → Register with ModelRegistry → Store in MLflow → Generate model_id → Trigger webhook notification [details: features/replace-redis-with-webhook/prd.md]

### DNS Resolution Flow  
- Resolve hostname → Check cache (5-min TTL) → Fallback to cached IP on failure → Emergency fallback via MLFLOW_FALLBACK_IP env var [details: features/dns-resolution-fallback/prd.md]

### Webhook Notification Flow
- Model registered → Generate HMAC signature → Send webhook POST with retry logic → Exponential backoff on failure → Circuit breaker for endpoint health [details: features/replace-redis-with-webhook/prd.md]

## Architecture Patterns

### Authentication & Security
- API key authentication with configurable rate limits (HOKUSAI_API_KEY)
- HMAC-SHA256 signature verification for webhooks using shared secret
- JWT token validation for inter-service communication with auth service
- MLflow proxy authentication through API keys (MLFLOW_TRACKING_TOKEN)

### Reliability Patterns
- DNS caching with TTL-based expiration and manual override capability
- Webhook retry with exponential backoff (2, 4, 8, 16, 32 seconds)
- Circuit breaker pattern for external endpoint health management
- Dual publishing mode for Redis to webhook migration support

### Service Communication
- Internal services use ECS service discovery (*.hokusai-development.local)
- External APIs accessed via ALB routing (api.hokus.ai, registry.hokus.ai)
- Webhook-based event notifications replacing Redis pub/sub
- Connection pooling for HTTP client performance

## Tech Stack & Conventions

### Core Technologies
- **Python 3.11**: Primary language for ML platform and API services
- **MLflow**: Model registry and experiment tracking backend
- **FastAPI**: REST API framework for model serving endpoints
- **PostgreSQL**: Database for MLflow metadata and model information
- **Docker Compose**: Local development environment orchestration

### Testing Framework
- **pytest**: Unit and integration testing framework
- **TDD approach**: Tests written before implementation
- **Chaos engineering**: DNS failure simulation tests
- **Load testing**: Concurrent request handling validation

## External Integrations

### AWS Services
- **ECS**: Container orchestration for API and MLFlow services
- **RDS PostgreSQL**: Managed database for MLflow metadata
- **S3**: Model artifact storage
- **CloudWatch**: Logs and metrics collection
- **ALB**: Load balancing and external routing

### Third-Party Services
- **Auth Service**: JWT token validation at auth.hokus.ai
- **Webhook Consumers**: External endpoints for model registration events
- **Vercel**: Serverless platform integration via webhooks

## Database Schema Insights

### MLflow Tables
- experiments: MLflow experiment metadata
- runs: Individual training run information
- models: Registered model versions and metadata
- Custom tables for model metadata and audit logs

### Model Registry Schema
- model_id: Unique identifier for registered models
- token_symbol: Associated blockchain token identifier
- baseline_metrics: Performance baseline data
- registered_version: Model version tracking

## API Patterns

### REST Endpoints
- `/api/v1/models`: Model listing and discovery
- `/api/v1/models/{id}/predict`: Inference endpoint
- `/api/v1/health`: Service health check with DNS status
- `/api/2.0/mlflow/*`: MLflow tracking API proxy

### Webhook Payload Structure
- model_id: Unique model identifier
- idempotency_key: Duplicate prevention UUID
- registered_version: Model version number
- timestamp: ISO 8601 registration time
- X-Hokusai-Signature header: HMAC verification

## Testing Patterns

### Test Organization
- Unit tests: `tests/unit/` for isolated component testing
- Integration tests: `tests/integration/` for service interaction
- Fast suite: Must complete in <2s for rapid feedback
- Integration suite: Slower tests with real DB/service connections

### Test Coverage Requirements
- 80%+ code coverage target
- Edge case and error condition testing
- Boundary condition validation (null values, max integers)
- Mock external dependencies appropriately

## Environment Configuration

### Standard Variables
- ENVIRONMENT: development|staging|production
- AWS_REGION: us-east-1
- HOKUSAI_API_KEY: API authentication key
- MLFLOW_TRACKING_URI: MLflow server endpoint
- WEBHOOK_URL: Model registration notification endpoint
- WEBHOOK_SECRET: HMAC signing secret

### Service Discovery URLs
- Internal MLFlow: http://mlflow.hokusai-development.local:5000
- Internal API: http://api.hokusai-development.local:8001
- Internal Auth: http://auth.hokusai-development.local:8000
- External endpoints via HTTPS (*.hokus.ai)

## Migration Strategies

### Redis to Webhook Migration
- Phase 1: Dual publishing to both Redis and webhooks
- Phase 2: Webhook primary with Redis fallback
- Phase 3: Complete Redis removal
- Toggle via ENABLE_REDIS_FALLBACK environment variable

### DNS Resolution Improvements  
- Replaced hardcoded IPs with service discovery names
- Added resilience through caching and fallback mechanisms
- Gradual rollout with monitoring and rollback capability

## Deployment Notes

### Docker Images
- API Service: hokusai/api:latest
- MLflow Service: hokusai/mlflow:latest
- Build and push to ECR for production deployment

### ECS Service Updates
- Cluster: hokusai-development
- Services: hokusai-api-development, hokusai-mlflow-development
- Force new deployment for updates

### Monitoring & Observability
- CloudWatch Logs: `/ecs/hokusai-api-development`, `/ecs/hokusai-mlflow-development`
- Custom metrics for predictions, latency, webhook delivery
- DNS resolution success rate tracking
- Alert on repeated failures