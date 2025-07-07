# Product Requirements Document: Model Registration from Hokusai Site

## Objective

Enable users to register and upload AI models that have been created on the Hokusai site, linking them to their associated tokens and validating their performance metrics against baseline requirements.

## User Personas

1. **Model Developer**: Technical user who has trained an AI model and created a token on the Hokusai site
2. **Data Scientist**: User who needs to register models for deployment in the ML pipeline
3. **Token Creator**: User who creates tokens in Draft form on the Hokusai site and needs to associate them with models

## Success Criteria

1. Users can successfully register models using a CLI command with token ID, model path, metric name, and baseline value
2. Models are uploaded to MLflow with proper metadata and tracking
3. The system validates metric values against baseline requirements
4. Model status is updated to 'registered' in the database upon successful validation
5. A "token_ready_for_deploy" event is emitted for downstream processes

## Technical Requirements

### Command Line Interface
Create a CLI command with the following syntax:
```
hokusai-ml-platform model register \
  --token-id XRAY \
  --model-path ./checkpoints/final \
  --metric auroc \
  --baseline 0.82
```

### Core Functionality
1. **Model Upload**: Upload the model artifact to MLflow model registry
2. **Database Integration**: Save the mlflow_run_id to the database for the specified token model
3. **Metric Validation**: Validate that the provided metric value meets or exceeds the baseline
4. **Status Update**: Mark model status as 'registered' in the database
5. **Event Emission**: Emit a "token_ready_for_deploy" event via pub/sub, webhook, or database watcher

### Data Flow
1. User creates token on Hokusai site (token created in Draft status)
2. User trains model locally or in their environment
3. User runs registration command with required parameters
4. System uploads model to MLflow
5. System validates metrics against baseline
6. System updates database with model metadata
7. System emits deployment ready event

### Error Handling
1. Validate token exists in Draft status before proceeding
2. Verify model path exists and is readable
3. Ensure metric name is valid and supported
4. Check baseline value is numeric and reasonable
5. Handle MLflow connection errors gracefully
6. Provide clear error messages for validation failures

### Integration Points
1. **Hokusai Site Database**: Read token information and update model status
2. **MLflow**: Upload models and track experiments
3. **Event System**: Emit events for downstream consumers
4. **CLI Framework**: Integrate with existing hokusai-ml-platform CLI