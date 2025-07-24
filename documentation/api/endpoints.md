---
id: api-endpoints
title: API Endpoints Reference
sidebar_label: API Endpoints
sidebar_position: 2
---

# API Endpoints Reference

This document provides a comprehensive reference for all Hokusai API endpoints, including the MLflow proxy endpoints.

## Base URL

All API endpoints are available at:
```
https://registry.hokus.ai/api
```

## Authentication

All endpoints require authentication using a Hokusai API key. Include the key in the Authorization header:

```bash
Authorization: Bearer hk_live_your_api_key_here
```

## MLflow Endpoints

Hokusai provides a complete MLflow API proxy at `/api/mlflow/*`. All standard MLflow REST API endpoints are supported.

### Base Path
```
https://registry.hokus.ai/api/mlflow
```

### Experiments

#### Search Experiments
```http
GET /api/mlflow/api/2.0/mlflow/experiments/search
```

Query parameters:
- `max_results` (int): Maximum number of experiments to return
- `page_token` (string): Pagination token
- `filter` (string): Filter expression
- `order_by` (string): Column to order by

Example:
```bash
curl -H "Authorization: Bearer ${HOKUSAI_API_KEY}" \
  "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search?max_results=10"
```

#### Create Experiment
```http
POST /api/mlflow/api/2.0/mlflow/experiments/create
```

Request body:
```json
{
  "name": "my-experiment",
  "artifact_location": "s3://bucket/path",
  "tags": [
    {"key": "team", "value": "ml-team"}
  ]
}
```

#### Get Experiment
```http
GET /api/mlflow/api/2.0/mlflow/experiments/get?experiment_id={id}
```

#### Update Experiment
```http
POST /api/mlflow/api/2.0/mlflow/experiments/update
```

Request body:
```json
{
  "experiment_id": "123",
  "new_name": "updated-experiment-name"
}
```

### Runs

#### Create Run
```http
POST /api/mlflow/api/2.0/mlflow/runs/create
```

Request body:
```json
{
  "experiment_id": "123",
  "start_time": 1234567890000,
  "tags": [
    {"key": "model_type", "value": "random_forest"}
  ]
}
```

#### Get Run
```http
GET /api/mlflow/api/2.0/mlflow/runs/get?run_id={id}
```

#### Update Run
```http
POST /api/mlflow/api/2.0/mlflow/runs/update
```

Request body:
```json
{
  "run_id": "abc123",
  "status": "FINISHED",
  "end_time": 1234567890000
}
```

#### Log Metric
```http
POST /api/mlflow/api/2.0/mlflow/runs/log-metric
```

Request body:
```json
{
  "run_id": "abc123",
  "key": "accuracy",
  "value": 0.92,
  "timestamp": 1234567890000,
  "step": 0
}
```

#### Log Parameter
```http
POST /api/mlflow/api/2.0/mlflow/runs/log-parameter
```

Request body:
```json
{
  "run_id": "abc123",
  "key": "learning_rate",
  "value": "0.01"
}
```

#### Log Batch
```http
POST /api/mlflow/api/2.0/mlflow/runs/log-batch
```

Request body:
```json
{
  "run_id": "abc123",
  "metrics": [
    {"key": "loss", "value": 0.23, "timestamp": 1234567890000, "step": 0}
  ],
  "params": [
    {"key": "batch_size", "value": "32"}
  ],
  "tags": [
    {"key": "framework", "value": "pytorch"}
  ]
}
```

#### Search Runs
```http
GET /api/mlflow/api/2.0/mlflow/runs/search
```

Query parameters:
- `experiment_ids` (array): List of experiment IDs
- `filter` (string): Filter expression
- `max_results` (int): Maximum results
- `order_by` (array): Columns to order by

### Model Registry

#### Create Registered Model
```http
POST /api/mlflow/api/2.0/mlflow/registered-models/create
```

Request body:
```json
{
  "name": "my-model",
  "tags": [
    {"key": "task", "value": "classification"}
  ]
}
```

#### Get Registered Model
```http
GET /api/mlflow/api/2.0/mlflow/registered-models/get?name={name}
```

#### Search Registered Models
```http
GET /api/mlflow/api/2.0/mlflow/registered-models/search
```

Query parameters:
- `filter` (string): Filter expression (e.g., "name='my-model'")
- `max_results` (int): Maximum results
- `page_token` (string): Pagination token

#### Update Registered Model
```http
POST /api/mlflow/api/2.0/mlflow/registered-models/update
```

Request body:
```json
{
  "name": "my-model",
  "description": "Updated model description"
}
```

#### Delete Registered Model
```http
POST /api/mlflow/api/2.0/mlflow/registered-models/delete
```

Request body:
```json
{
  "name": "my-model"
}
```

### Model Versions

#### Create Model Version
```http
POST /api/mlflow/api/2.0/mlflow/model-versions/create
```

Request body:
```json
{
  "name": "my-model",
  "source": "runs:/abc123/model",
  "run_id": "abc123",
  "tags": [
    {"key": "stage", "value": "staging"}
  ]
}
```

#### Get Model Version
```http
GET /api/mlflow/api/2.0/mlflow/model-versions/get?name={name}&version={version}
```

#### Update Model Version
```http
POST /api/mlflow/api/2.0/mlflow/model-versions/update
```

Request body:
```json
{
  "name": "my-model",
  "version": "1",
  "description": "Production-ready version"
}
```

#### Transition Model Version Stage
```http
POST /api/mlflow/api/2.0/mlflow/model-versions/transition-stage
```

Request body:
```json
{
  "name": "my-model",
  "version": "1",
  "stage": "Production",
  "archive_existing_versions": true
}
```

#### Search Model Versions
```http
GET /api/mlflow/api/2.0/mlflow/model-versions/search
```

Query parameters:
- `filter` (string): Filter expression
- `max_results` (int): Maximum results
- `order_by` (array): Columns to order by

#### Set Model Version Tag
```http
POST /api/mlflow/api/2.0/mlflow/model-versions/set-tag
```

Request body:
```json
{
  "name": "my-model",
  "version": "1",
  "key": "hokusai_token_id",
  "value": "my-token"
}
```

### Artifacts

#### Download Artifacts
```http
GET /api/mlflow/api/2.0/mlflow-artifacts/artifacts/{run_id}/{path}
```

Example:
```bash
curl -H "Authorization: Bearer ${HOKUSAI_API_KEY}" \
  "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow-artifacts/artifacts/abc123/model/model.pkl" \
  -o model.pkl
```

#### Upload Artifacts
```http
PUT /api/mlflow/api/2.0/mlflow-artifacts/artifacts/{run_id}/{path}
```

Example:
```bash
curl -X PUT -H "Authorization: Bearer ${HOKUSAI_API_KEY}" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @model.pkl \
  "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow-artifacts/artifacts/abc123/model/model.pkl"
```

### Metrics

#### Get Metric History
```http
GET /api/mlflow/api/2.0/mlflow/metrics/get-history
```

Query parameters:
- `run_id` (string): Run ID
- `metric_key` (string): Metric name

## Hokusai-Specific Endpoints

### Model Registry (Hokusai)

#### Register Tokenized Model
```http
POST /api/models/register-tokenized
```

Request body:
```json
{
  "model_uri": "runs:/abc123/model",
  "model_name": "my-model",
  "token_id": "my-token",
  "metric_name": "accuracy",
  "baseline_value": 0.85
}
```

#### Get Model by Token
```http
GET /api/models/by-token/{token_id}
```

### Health Checks

#### MLflow Health Check
```http
GET /api/health/mlflow
```

Response:
```json
{
  "status": "healthy",
  "mlflow_server": "http://mlflow.hokusai-development.local:5000",
  "checks": {
    "connectivity": {
      "status": "healthy",
      "message": "MLflow server is reachable"
    },
    "experiments_api": {
      "status": "healthy",
      "message": "Experiments API is functional"
    },
    "artifacts_api": {
      "status": "enabled",
      "message": "Artifact serving is configured"
    }
  }
}
```

#### Detailed Health Check
```http
GET /api/health/mlflow/detailed
```

## Error Responses

All endpoints return standard HTTP status codes and error messages:

### 400 Bad Request
```json
{
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "Parameter 'name' is required"
  }
}
```

### 401 Unauthorized
```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or missing API key"
  }
}
```

### 404 Not Found
```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Model 'my-model' not found"
  }
}
```

### 429 Too Many Requests
```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Try again in 60 seconds"
  }
}
```

### 500 Internal Server Error
```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "An internal error occurred"
  }
}
```

## Rate Limiting

API requests are rate limited based on your API key tier:
- **Free tier**: 100 requests per minute
- **Standard tier**: 1000 requests per minute
- **Enterprise tier**: Custom limits

Rate limit headers are included in responses:
- `X-RateLimit-Limit`: Your rate limit
- `X-RateLimit-Remaining`: Requests remaining
- `X-RateLimit-Reset`: Time when limit resets

## Best Practices

1. **Use pagination**: For search endpoints, use pagination to handle large result sets
2. **Handle errors**: Implement exponential backoff for rate limit errors
3. **Batch operations**: Use batch endpoints when logging multiple metrics/parameters
4. **Compress artifacts**: Compress large model files before uploading
5. **Use filters**: Use filter expressions to reduce response size

## SDK Support

While the REST API is available for any language, we provide official SDKs:

### Python
```bash
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform
```

### Using with MLflow Client
```python
import mlflow
mlflow.set_tracking_uri("https://registry.hokus.ai/api/mlflow")
```

### Direct API Calls
```python
import requests

headers = {"Authorization": f"Bearer {api_key}"}
response = requests.get(
    "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search",
    headers=headers
)
```