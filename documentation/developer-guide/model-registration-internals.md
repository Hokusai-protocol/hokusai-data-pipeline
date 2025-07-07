# Model Registration Internals

This guide provides detailed information about the internal implementation of the model registration feature in the Hokusai ML Platform.

## Architecture Overview

The model registration system consists of several components working together:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   CLI Interface │────▶│ Validation Layer │────▶│ Database Layer  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                       │                         │
         │                       │                         │
         ▼                       ▼                         ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ MLflow Registry │     │  Event System    │     │ Error Handling  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## Component Details

### 1. CLI Interface (`src/cli/model.py`)

The CLI provides the user-facing interface for model registration:

```python
@model.command()
@click.option('--token-id', required=True, help='Token ID created on Hokusai site')
@click.option('--model-path', required=True, type=click.Path(exists=True))
@click.option('--metric', required=True, help='Performance metric name')
@click.option('--baseline', required=True, type=float)
def register(token_id, model_path, metric, baseline, ...):
    """Register a model created on the Hokusai site"""
```

Key responsibilities:
- Parse command-line arguments
- Orchestrate the registration workflow
- Handle errors and provide user feedback

### 2. Database Integration (`src/database/`)

#### Configuration (`config.py`)
Manages database connection settings with support for multiple sources:

```python
class DatabaseConfig:
    def __init__(self, host=None, port=None, database=None, ...):
        self.host = host or os.getenv("HOKUSAI_DB_HOST", "localhost")
        # ... other configuration
```

#### Models (`models.py`)
Defines the data structures:

```python
class ModelStatus(Enum):
    DRAFT = "draft"
    REGISTERING = "registering"
    REGISTERED = "registered"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ARCHIVED = "archived"

@dataclass
class TokenModel:
    token_id: str
    model_status: ModelStatus
    mlflow_run_id: Optional[str]
    # ... other fields
```

#### Operations (`operations.py`)
Provides database operations:

```python
class TokenOperations:
    def validate_token_status(self, token_id: str) -> bool:
        """Validate if token exists and is in DRAFT status"""
        
    def save_mlflow_run_id(self, token_id: str, mlflow_run_id: str, ...):
        """Save MLflow run ID and update status"""
```

### 3. Validation System (`src/validation/`)

#### Metric Validation (`metrics.py`)
Validates metric names and values:

```python
class SupportedMetrics(Enum):
    ACCURACY = "accuracy"
    AUROC = "auroc"
    F1 = "f1"
    # ... more metrics

class MetricValidator:
    def validate_metric_name(self, metric_name: str) -> bool:
        """Check if metric is supported"""
        
    def validate_baseline(self, metric_name: str, baseline: float) -> bool:
        """Validate baseline value for metric"""
```

#### Baseline Comparison (`baseline.py`)
Compares model performance against baseline:

```python
class BaselineComparator:
    def validate_improvement(self, current_value, baseline_value, metric_name):
        """Comprehensive validation of model improvement"""
        return {
            "meets_baseline": comparison != ComparisonResult.DEGRADED,
            "improvement": improvement,
            "improvement_percentage": improvement_pct
        }
```

### 4. Event System (`src/events/`)

#### Event Publisher (`publisher.py`)
Manages event creation and distribution:

```python
class EventPublisher:
    def publish(self, event_type: EventType, payload: Dict[str, Any]) -> bool:
        """Publish event to all registered handlers"""
        
    def publish_token_ready(self, token_id: str, mlflow_run_id: str):
        """Convenience method for token_ready_for_deploy event"""
```

#### Event Handlers (`handlers.py`)
Different backends for event delivery:

```python
class WebhookHandler(EventHandler):
    """Send events via HTTP webhooks"""
    
class PubSubHandler(EventHandler):
    """Publish events to Google Pub/Sub"""
    
class DatabaseWatcherHandler(EventHandler):
    """Write events to database for polling"""
```

### 5. Error Handling (`src/errors/`)

#### Custom Exceptions (`exceptions.py`)
Domain-specific error types:

```python
class TokenNotFoundError(HokusaiError):
    """Token doesn't exist in database"""
    
class MetricValidationError(HokusaiError):
    """Metric validation failed"""
    
class MLflowError(HokusaiError):
    """MLflow operation failed"""
```

#### Error Handler (`handlers.py`)
Centralized error handling with retry logic:

```python
class ErrorHandler:
    def handle_error(self, error, context=None, raise_error=True, max_retries=0):
        """Handle errors with logging and optional retry"""
```

## Registration Workflow

The registration process follows these steps:

### Step 1: Input Validation
```python
validator = MetricValidator()
if not validator.validate_metric_name(metric):
    raise MetricValidationError(metric, reason="Unsupported metric")
```

### Step 2: Database Connection
```python
db_conf = DatabaseConfig.from_file(db_config) or DatabaseConfig.from_env()
with DatabaseConnection(db_conf).session() as db:
    token_ops = TokenOperations(db)
    token_ops.validate_token_status(token_id)
```

### Step 3: MLflow Upload
```python
with mlflow.start_run() as run:
    mlflow.log_artifact(model_path)
    mlflow.log_param("token_id", token_id)
    mlflow.set_tag("hokusai_token_id", token_id)
    
    mlflow.register_model(
        f"runs:/{run.info.run_id}/model",
        f"hokusai-{token_id}"
    )
```

### Step 4: Performance Validation
```python
comparator = BaselineComparator()
validation_result = comparator.validate_improvement(
    current_value=actual_metric_value,
    baseline_value=baseline,
    metric_name=metric
)
```

### Step 5: Status Update
```python
token_ops.save_mlflow_run_id(
    token_id=token_id,
    mlflow_run_id=mlflow_run_id,
    metric_name=metric,
    metric_value=actual_metric_value,
    baseline_value=baseline
)
```

### Step 6: Event Emission
```python
publisher = EventPublisher()
publisher.register_handler(WebhookHandler(webhook_url))
publisher.publish_token_ready(token_id, mlflow_run_id, metadata)
```

## Database Schema

The system expects the following database structure:

```sql
CREATE TABLE tokens (
    token_id VARCHAR(255) PRIMARY KEY,
    model_status VARCHAR(50) NOT NULL,
    mlflow_run_id VARCHAR(255),
    metric_name VARCHAR(100),
    metric_value FLOAT,
    baseline_value FLOAT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    metadata JSONB
);

CREATE TABLE events (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    source VARCHAR(100),
    timestamp TIMESTAMP,
    payload JSONB,
    processed BOOLEAN DEFAULT FALSE
);
```

## MLflow Integration

The system integrates with MLflow for model storage and tracking:

1. **Model Storage**: Models are uploaded as artifacts
2. **Parameter Tracking**: Token ID, metric name, baseline value
3. **Tagging**: Hokusai-specific tags for filtering
4. **Model Registry**: Models registered with pattern `hokusai-{token_id}`

## Testing Strategy

### Unit Tests
- CLI command parsing
- Validation logic
- Event publishing
- Error handling

### Integration Tests
- Database operations
- MLflow integration
- End-to-end workflow
- Error scenarios

### Mock Strategy
```python
@patch('cli.model.DatabaseConnection')
@patch('cli.model.mlflow')
def test_registration(mock_mlflow, mock_db):
    # Configure mocks
    mock_mlflow.start_run.return_value.__enter__.return_value.info.run_id = "test-id"
    # Test registration flow
```

## Configuration Best Practices

1. **Environment Variables**: Use for production deployments
2. **Configuration Files**: Use for development/testing
3. **Secrets Management**: Never commit passwords to version control
4. **Connection Pooling**: Implement for production database connections

## Performance Considerations

1. **Model Upload**: Large models should be uploaded asynchronously
2. **Database Connections**: Use connection pooling
3. **Event Delivery**: Consider async event publishing for webhooks
4. **Retry Logic**: Implement exponential backoff for transient failures

## Security Considerations

1. **Authentication**: Database credentials should be encrypted
2. **Authorization**: Validate user permissions for token access
3. **Webhook Security**: Use HTTPS and authentication headers
4. **Input Validation**: Sanitize all user inputs

## Extending the System

### Adding New Metrics
1. Add to `SupportedMetrics` enum
2. Define value ranges in `MetricValidator`
3. Update documentation

### Adding New Event Handlers
1. Inherit from `EventHandler` base class
2. Implement `can_handle()` and `handle()` methods
3. Register with `EventPublisher`

### Supporting New Databases
1. Update `DatabaseConfig` for connection strings
2. Adapt SQL queries in `TokenOperations`
3. Add database-specific error handling

## Monitoring and Debugging

### Logging
Configure logging level:
```python
configure_logging(level="DEBUG")
```

### Metrics to Track
- Registration success/failure rates
- Average registration time
- Event delivery success rates
- Database connection pool utilization

### Common Issues
1. **Token Status**: Use `TokenOperations.list_tokens_by_status()`
2. **MLflow Connection**: Check with `mlflow.get_tracking_uri()`
3. **Event Delivery**: Monitor handler return values

## Future Enhancements

1. **Async Processing**: Make model upload asynchronous
2. **Batch Registration**: Support multiple model registration
3. **Model Versioning**: Support multiple versions per token
4. **Automated Testing**: Add model performance calculation
5. **Audit Trail**: Complete audit log of all operations