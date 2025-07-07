# Model Registration Feature

This directory contains the implementation of the model registration feature for the Hokusai ML Platform. This feature enables users to register AI models that have been created on the Hokusai site, linking them to tokens and validating their performance.

## Directory Structure

```
src/
├── cli/
│   └── model.py              # CLI commands for model management
├── database/
│   ├── __init__.py
│   ├── config.py             # Database configuration management
│   ├── connection.py         # Database connection handling
│   ├── models.py             # Data models (TokenModel, ModelStatus)
│   └── operations.py         # Database operations for tokens
├── validation/
│   ├── __init__.py
│   ├── metrics.py            # Metric validation and supported metrics
│   └── baseline.py           # Baseline comparison logic
├── events/
│   ├── __init__.py
│   ├── publisher.py          # Event publishing system
│   └── handlers.py           # Event handlers (webhook, pubsub, etc.)
└── errors/
    ├── __init__.py
    ├── exceptions.py         # Custom exception classes
    └── handlers.py           # Error handling and logging
```

## Quick Start

### Installation

```bash
pip install -e ./hokusai-ml-platform
```

### Basic Usage

```bash
hokusai model register \
  --token-id XRAY \
  --model-path ./model.pkl \
  --metric auroc \
  --baseline 0.82
```

## Key Components

### 1. CLI Interface (`cli/model.py`)
- Provides `hokusai model` command group
- Subcommands: `register`, `status`, `list`
- Handles user interaction and orchestrates the workflow

### 2. Database Layer (`database/`)
- **config.py**: Manages database configuration from files or environment
- **connection.py**: Provides database connection management
- **models.py**: Defines `TokenModel` and `ModelStatus` enum
- **operations.py**: Implements token validation and status updates

### 3. Validation System (`validation/`)
- **metrics.py**: Defines supported metrics and validation rules
- **baseline.py**: Compares model performance against baselines

### 4. Event System (`events/`)
- **publisher.py**: Core event publishing functionality
- **handlers.py**: Multiple event delivery backends (webhook, console, database)

### 5. Error Handling (`errors/`)
- **exceptions.py**: Domain-specific exception classes
- **handlers.py**: Centralized error handling with retry logic

## Configuration

### Environment Variables

```bash
# Database Configuration
export HOKUSAI_DB_HOST=localhost
export HOKUSAI_DB_PORT=5432
export HOKUSAI_DB_NAME=hokusai
export HOKUSAI_DB_USER=hokusai_user
export HOKUSAI_DB_PASSWORD=secure_password
export HOKUSAI_DB_TYPE=postgresql

# MLflow Configuration
export MLFLOW_TRACKING_URI=http://localhost:5000

# Logging
export HOKUSAI_LOG_LEVEL=INFO
```

### Configuration File

Create a JSON or YAML file:

```json
{
  "host": "localhost",
  "port": 5432,
  "database": "hokusai",
  "username": "hokusai_user",
  "password": "secure_password",
  "db_type": "postgresql"
}
```

## Development

### Running Tests

```bash
# Unit tests
pytest tests/unit/test_model_registration_cli.py
pytest tests/unit/test_validation_system.py
pytest tests/unit/test_event_system.py

# Integration tests
pytest tests/integration/test_model_registration_integration.py

# All tests
pytest tests/
```

### Adding New Features

#### Adding a New Metric
1. Add to `SupportedMetrics` enum in `validation/metrics.py`
2. Define value ranges in `MetricValidator._get_metric_ranges()`
3. Update documentation

#### Adding a New Event Handler
1. Create new handler class inheriting from `EventHandler`
2. Implement `can_handle()` and `handle()` methods
3. Add to `events/__init__.py` exports

#### Supporting a New Database
1. Update `DatabaseConfig.get_connection_string()` in `database/config.py`
2. Adapt queries in `database/operations.py` if needed
3. Add database-specific error handling

## API Usage

The components can be used programmatically:

```python
from database import DatabaseConfig, DatabaseConnection, TokenOperations
from validation import MetricValidator, BaselineComparator
from events import EventPublisher, WebhookHandler

# Validate metrics
validator = MetricValidator()
if validator.validate_metric_name("auroc"):
    print("Valid metric")

# Check token status
config = DatabaseConfig.from_env()
with DatabaseConnection(config).session() as db:
    ops = TokenOperations(db)
    ops.validate_token_status("XRAY")

# Publish events
publisher = EventPublisher()
publisher.register_handler(WebhookHandler("https://api.example.com/webhook"))
publisher.publish_token_ready("XRAY", "mlflow-run-123")
```

## Error Handling

The system provides detailed error messages:

- `TokenNotFoundError`: Token doesn't exist
- `TokenInvalidStatusError`: Token not in correct status
- `MetricValidationError`: Invalid metric or value
- `DatabaseConnectionError`: Database connection issues
- `MLflowError`: MLflow operation failures

## Event System

Events are published for downstream consumption:

### Event Types
- `token_ready_for_deploy`: Model successfully registered
- `model_registered`: Detailed registration information

### Event Payload Example
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "token_ready_for_deploy",
  "source": "hokusai-ml-platform",
  "timestamp": "2024-01-15T10:30:00Z",
  "payload": {
    "token_id": "XRAY",
    "mlflow_run_id": "abc123",
    "metadata": {
      "metric_name": "auroc",
      "metric_value": 0.85,
      "baseline_value": 0.82
    }
  }
}
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure `src` is in Python path
2. **Database Connection**: Check credentials and network access
3. **MLflow Issues**: Verify tracking server is running
4. **Event Delivery**: Check webhook URLs and authentication

### Debug Mode

Enable debug logging:
```bash
export HOKUSAI_LOG_LEVEL=DEBUG
```

## Contributing

1. Follow existing code patterns
2. Add tests for new functionality
3. Update documentation
4. Run tests before submitting PR

## License

This feature is part of the Hokusai ML Platform and follows the same license terms.