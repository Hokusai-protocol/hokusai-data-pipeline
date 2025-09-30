# Product Requirements Document: Serve Models via API

## Objectives
Enable users to access deployed models through a REST API for inference, providing a standardized interface for model consumption across different infrastructure providers.

## Target Personas

### Primary: ML Engineers
- Need to deploy and serve trained models for production use
- Require simple, reliable API access to models
- Value quick deployment without infrastructure complexity

### Secondary: Application Developers
- Need to integrate ML models into applications
- Require consistent API interface regardless of backend provider
- Value clear documentation and predictable response formats

## Success Criteria
1. Users can register a model and automatically get an inference API endpoint
2. API validates user authentication via existing API key system
3. Support for at least one infrastructure provider (AWS, HuggingFace, or Together.AI)
4. API response time under 2 seconds for CPU inference
5. 99% uptime for deployed endpoints

## Technical Requirements

### Core Functionality
- Automatic API endpoint creation when model is registered in MLFlow
- REST API with JSON request/response format
- Integration with existing auth service for API key validation
- Support for CPU inference initially (GPU support in future iteration)

### Infrastructure Provider
Start with HuggingFace Inference Endpoints as the easiest provider:
- Simple deployment API
- Built-in model serving capabilities
- Pay-per-hour pricing model
- No complex infrastructure setup

### API Design
- Endpoint pattern: `/api/v1/models/{model_id}/predict`
- Method: POST
- Input: JSON payload with model inputs
- Output: JSON response with predictions
- Authentication: Bearer token (API key) in header

### Integration Points
- MLFlow registry for model metadata
- Auth service (auth.hokus.ai) for API key validation
- Infrastructure provider APIs for deployment
- Existing API service structure at api.hokus.ai

## Out of Scope (First Iteration)
- Usage tracking and metering
- Billing integration
- Custom rate limits per user
- GPU inference support
- Multiple provider support
- Model versioning in API
- Batch inference

## Implementation Phases

### Phase 1: Foundation (Week 1)
- Design API schema and database models
- Create provider abstraction interface
- Set up HuggingFace integration

### Phase 2: Core API (Week 2)
- Implement prediction endpoint
- Add authentication middleware
- Create model deployment service

### Phase 3: MLFlow Integration (Week 3)
- Hook into model registration events
- Automatic endpoint provisioning
- Model metadata synchronization

### Phase 4: Testing & Documentation (Week 4)
- Comprehensive test suite
- API documentation
- Integration testing

### Phase 5: Deployment (Week 5)
- Deploy to development environment
- Monitor and iterate
- Prepare for production rollout

## Technical Architecture

### Components
1. **API Service** - FastAPI application handling inference requests
2. **Deployment Service** - Manages model deployment to providers
3. **Provider Adapters** - Abstract interface for different providers
4. **Database Models** - Track deployed models and endpoints

### Database Schema
```
deployed_models:
  - id: UUID
  - model_id: String (MLFlow model ID)
  - provider: String
  - endpoint_url: String
  - status: String
  - created_at: DateTime
  - updated_at: DateTime
```

### API Flow
1. Client sends POST request with API key
2. Validate API key with auth service
3. Look up deployed model endpoint
4. Forward request to provider
5. Return predictions to client

## Risks and Mitigations

### Risk: Provider Outages
**Mitigation**: Implement retry logic and circuit breakers

### Risk: Cost Overruns
**Mitigation**: Start with CPU only, implement cost monitoring

### Risk: Model Compatibility
**Mitigation**: Validate models before deployment, clear documentation on supported types

## Metrics
- Number of models deployed
- API request volume
- Average response time
- Error rate
- Provider costs
- User adoption rate