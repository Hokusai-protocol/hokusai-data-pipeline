# Product Requirements Document: Hokusai ML Platform Package

## Objectives

Package the hokusai-data-pipeline's ML platform capabilities into a reusable Python package called `hokusai-ml-platform` that can be imported and used by other Hokusai projects, particularly GTM-backend.

## Personas

### Primary User: ML Engineers
- Need to integrate Hokusai's ML infrastructure into their projects
- Want consistent model management across different services
- Require tracking of model improvements and contributor attribution

### Secondary User: Data Scientists
- Need to register and version models
- Want to track experiments and model lineage
- Require A/B testing capabilities for model comparison

## Success Criteria

1. Create a pip-installable package with core ML services
2. Maintain compatibility with existing hokusai-data-pipeline functionality
3. Provide clear separation between core platform and pipeline-specific features
4. Enable GTM-backend to use model registry and tracking features
5. Support both library import and API client usage patterns

## Technical Requirements

### Package Structure
Create a Python package with the following structure:
- Core ML infrastructure modules (models, registry, versioning, A/B testing, inference)
- MLOps tracking modules (experiments, performance, lineage)
- Pipeline components (data, training, evaluation, attestation)
- API clients and schemas
- Utility modules (config, logging, metrics)

### Dependencies
- Core dependencies: mlflow, metaflow, redis, fastapi, pydantic
- Optional dependencies for specific use cases (gtm, pipeline)

### Key Features
1. **Model Registry**: Central registry for all models with MLflow integration
2. **Version Management**: Track model versions and enable rollbacks
3. **A/B Testing Framework**: Compare model performance with traffic routing
4. **Inference Pipeline**: Optimized inference with caching
5. **Experiment Tracking**: Track all experiments and model improvements
6. **Performance Tracking**: Monitor model performance deltas
7. **Model Lineage**: Track improvement history and contributor impact
8. **Attestation Support**: Generate ZK-ready attestations for improvements

## Implementation Tasks

### Setup and Configuration
1. Create new package structure under `hokusai-ml-platform/`
2. Set up pyproject.toml with proper dependencies and optional groups
3. Configure package metadata and entry points

### Core Infrastructure
1. Extract and refactor model abstraction layer from existing codebase
2. Implement ModelRegistry class with MLflow integration
3. Create ModelVersionManager for version control
4. Build A/B testing framework with traffic routing
5. Develop inference pipeline with Redis caching

### MLOps Tracking
1. Implement ExperimentManager for experiment tracking
2. Create PerformanceTracker for delta calculations
3. Build model lineage tracking system
4. Integrate with existing attestation generation

### API Layer
1. Create FastAPI endpoints for model management
2. Develop Python client library for API access
3. Define shared schemas for data exchange
4. Implement authentication and authorization

### Integration
1. Ensure backward compatibility with hokusai-data-pipeline
2. Create migration guide for existing code
3. Build example integrations for GTM-backend
4. Document API usage patterns

### Testing and Documentation
1. Write comprehensive unit tests for all modules
2. Create integration tests with mock services
3. Develop usage examples and tutorials
4. Generate API documentation

## Constraints

- Must maintain compatibility with existing hokusai-data-pipeline workflows
- Should not require changes to current Metaflow pipeline structure
- Must support both synchronous and asynchronous usage patterns
- Should minimize dependencies for lightweight installations

## Deliverables

1. `hokusai-ml-platform` Python package
2. Complete test suite with >80% coverage
3. API documentation and client libraries
4. Migration guide from embedded to package usage
5. Example implementations for common use cases