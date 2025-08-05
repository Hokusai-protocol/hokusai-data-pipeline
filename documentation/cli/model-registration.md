# Model Registration CLI

The Hokusai ML Platform provides a command-line interface for registering AI models that have been created on the Hokusai site. This guide covers the model registration workflow and all available commands.

## Overview

The Hokusai model registration CLI provides a simple way to register your trained models with the Hokusai platform. It uses the Hokusai API to:

- Upload your model to MLflow 
- Validate performance metrics
- Associate the model with a Hokusai token
- Prepare the model for deployment

When users create tokens on the Hokusai site, they start in "Draft" status. The model registration process links a trained model to its token and validates performance metrics.

## Prerequisites

Before registering a model, ensure you have:

1. Created a token on the Hokusai site (token must be in "Draft" status)
2. Trained your model and saved it to disk
3. Calculated your model's performance metric
4. A Hokusai API key (obtain from https://hokus.ai/settings/api)

## Installation

Install from the repository:

```bash
cd /path/to/hokusai-data-pipeline
pip install -e ./hokusai-ml-platform
```

## Basic Usage

### Register a Model

The primary command for model registration is:

```bash
hokusai model register \
  --token-id XRAY \
  --model-path ./checkpoints/final_model.pkl \
  --metric auroc \
  --baseline 0.82
```

This command will:
1. Validate the token exists and is in "Draft" status
2. Upload the model to MLflow
3. Validate the model's performance meets the baseline requirement
4. Update the model status to "registered" in the database
5. Emit a "token_ready_for_deploy" event

### Command Options

| Option | Required | Description | Example |
|--------|----------|-------------|---------|
| `--token-id` | Yes | Token ID created on Hokusai site | `XRAY` |
| `--model-path` | Yes | Path to model file/directory | `./model.pkl` |
| `--metric` | Yes | Performance metric name | `auroc`, `accuracy`, `f1` |
| `--baseline` | Yes | Baseline performance requirement | `0.82` |
| `--mlflow-uri` | No | MLflow tracking server URI | `http://localhost:5000` |
| `--db-config` | No | Path to database config file (for local dev) | `./db_config.json` |
| `--webhook-url` | No | Webhook URL for events | `https://api.example.com/webhook` |

## Supported Metrics

The platform supports various metrics for different model types:

### Classification Metrics
- `accuracy` - Overall accuracy (0-1)
- `auroc` / `auc` - Area Under ROC Curve (0-1)
- `f1` - F1 Score (0-1)
- `precision` - Precision (0-1)
- `recall` - Recall (0-1)

### Regression Metrics
- `mse` - Mean Squared Error (≥0)
- `rmse` - Root Mean Squared Error (≥0)
- `mae` - Mean Absolute Error (≥0)
- `r2` - R-squared (≤1)

### Custom Metrics
- `reply_rate` - Email reply rate (0-1)
- `conversion_rate` - Conversion rate (0-1)
- `engagement_score` - User engagement score (≥0)

## Configuration

### API Authentication

Hokusai uses API key authentication. Set your API key as an environment variable:

```bash
export HOKUSAI_API_KEY="your-api-key-here"
```

You can obtain your API key from:
1. Log in to https://hokus.ai
2. Navigate to Settings → API Keys  
3. Click "Generate New Key"
4. Copy the key and store it securely

### Database Configuration (Optional)

**Note**: Most users don't need database configuration as the CLI uses the Hokusai API. Database configuration is only needed for advanced use cases or local development.

For local development, you can configure a local database:

```bash
# For local development only
export HOKUSAI_DB_HOST=localhost
export HOKUSAI_DB_PORT=5432
export HOKUSAI_DB_NAME=hokusai_dev
```

### MLflow Configuration

The Hokusai platform uses MLflow for model tracking and registry. The MLflow server is accessed through the API proxy at `https://registry.hokus.ai/api/mlflow`.

#### Default Configuration

The SDK automatically configures MLflow to use the Hokusai server:

```bash
# MLflow is automatically configured to use registry.hokus.ai/api/mlflow
hokusai model register \
  --token-id XRAY \
  --model-path ./model.pkl \
  --metric auroc \
  --baseline 0.82
```

#### Custom MLflow Server

To use a different MLflow server:

```bash
# Via environment variable
export MLFLOW_TRACKING_URI=http://your-mlflow-server:5000

# Or via command line
hokusai model register ... --mlflow-uri http://your-mlflow-server:5000
```

#### Local Development Mode

For local development without MLflow server access:

```bash
# Enable mock mode
export HOKUSAI_MOCK_MODE=true

# Now commands will run without connecting to MLflow
hokusai model register \
  --token-id XRAY \
  --model-path ./model.pkl \
  --metric auroc \
  --baseline 0.82
```

In mock mode:
- Model registration is simulated
- No actual MLflow connection required
- Useful for testing and development

For more details on MLflow configuration, see the [MLflow Access Guide](../getting-started/mlflow-access.md).

## Event Notifications

The model registration process emits events that can be consumed by downstream systems:

### Event Types
- `token_ready_for_deploy` - Emitted when model is successfully registered
- `model_registered` - Detailed registration event with metrics

### Event Handlers

1. **Webhook**: Send events to an HTTP endpoint
```bash
hokusai model register ... --webhook-url https://api.example.com/events
```

2. **Console**: Events are always logged to console for debugging

3. **Database**: Events can be written to database for polling systems

## Other Commands

### Check Model Status

```bash
hokusai model status --token-id XRAY
```

### List Registered Models

```bash
hokusai model list
```

## Error Handling

The CLI provides detailed error messages for common issues:

- **Token Not Found**: The specified token doesn't exist in the database
- **Invalid Token Status**: Token is not in "Draft" status
- **Metric Validation Failed**: Metric name is unsupported or value is invalid
- **Performance Below Baseline**: Model doesn't meet baseline requirement
- **Database Connection Failed**: Unable to connect to database
- **MLflow Error**: Issues with model upload or registration

## Examples

### Basic Registration

```bash
hokusai model register \
  --token-id CHEST-XRAY-V2 \
  --model-path ./models/chest_xray_classifier.h5 \
  --metric auroc \
  --baseline 0.85
```

### With Custom Configuration

```bash
hokusai model register \
  --token-id MSG-AI \
  --model-path ./checkpoints/gpt_finetuned/ \
  --metric reply_rate \
  --baseline 0.134 \
  --db-config ./config/production.json \
  --mlflow-uri https://registry.hokus.ai/api/mlflow \
  --webhook-url https://api.hokus.ai/webhooks/model-events
```

### Using Environment Variables

```bash
export HOKUSAI_DB_HOST=prod-db.hokus.ai
export HOKUSAI_DB_USER=ml_platform_user
export MLFLOW_TRACKING_URI=https://registry.hokus.ai/api/mlflow

hokusai model register \
  --token-id SENTIMENT-V3 \
  --model-path ./sentiment_model.pkl \
  --metric accuracy \
  --baseline 0.92
```

## Troubleshooting

### Common Issues

1. **"Token not found"**
   - Verify the token ID is correct
   - Check you have access to the correct database
   - Ensure the token was created on the Hokusai site

2. **"Token is not in Draft status"**
   - Token may already be registered
   - Check token status with `hokusai model status --token-id <ID>`

3. **"Model performance does not meet baseline"**
   - Review your model's actual performance
   - Ensure you're using the correct metric
   - Consider retraining with improved data/parameters

4. **"Failed to connect to MLflow"**
   - Check MLflow server is running
   - Verify the tracking URI is correct
   - Ensure network connectivity

### Debug Mode

For detailed logging, set the log level:

```bash
export HOKUSAI_LOG_LEVEL=DEBUG
hokusai model register ...
```

## API Integration

The model registration functionality can also be accessed programmatically:

```python
from hokusai.core import ModelRegistry
from hokusai.tracking import MLflowClient

# Initialize components
registry = ModelRegistry()
mlflow_client = MLflowClient()

# Register model
result = registry.register_model(
    token_id="XRAY",
    model_path="./model.pkl",
    metric_name="auroc",
    metric_value=0.85,
    baseline_value=0.82
)

print(f"Model registered with run ID: {result.mlflow_run_id}")
```

## Next Steps

After successful model registration:

1. Monitor the deployment status on the Hokusai site
2. Set up A/B testing if needed
3. Configure model serving infrastructure
4. Monitor model performance in production

## See Also

- [Model Registry Documentation](../core-features/model-registry.md)
- [DeltaOne Detection](../core-features/deltaone-detection.md)
- [API Reference](../api-reference/index.md)