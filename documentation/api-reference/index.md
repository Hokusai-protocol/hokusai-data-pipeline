---
id: api-reference
title: API Reference
sidebar_label: Overview
sidebar_position: 1
---

# API Reference

Complete reference documentation for the Hokusai ML Platform API.

## Overview

The Hokusai API provides programmatic access to all platform features:

- **Model Management**: Register, version, and retrieve models
- **Data Contribution**: Submit datasets for model improvement
- **Performance Tracking**: Monitor metrics and DeltaOne achievements
- **Reward System**: Check and claim token rewards
- **DSPy Execution**: Run prompt optimization pipelines

## Base URL

```
https://api.hokus.ai/v1
```

For local development:
```
http://localhost:8000/api/v1
```

## Authentication

All API requests require authentication using an API key:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://api.hokus.ai/v1/models
```

In Python:
```python
import requests

headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}

response = requests.get(
    "https://api.hokus.ai/v1/models",
    headers=headers
)
```

## Response Format

All responses follow a consistent format:

### Success Response
```json
{
  "success": true,
  "data": {
    // Response data
  },
  "metadata": {
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_123abc"
  }
}
```

### Error Response
```json
{
  "success": false,
  "error": {
    "code": "MODEL_NOT_FOUND",
    "message": "Model 'my-model' not found",
    "details": {
      "model_name": "my-model"
    }
  },
  "metadata": {
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_456def"
  }
}
```

## Rate Limiting

API requests are rate-limited based on your plan:

| Plan | Requests/Hour | Requests/Day |
|------|---------------|--------------|
| Free | 100 | 1,000 |
| Pro | 1,000 | 10,000 |
| Enterprise | Unlimited | Unlimited |

Rate limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1642258800
```

## Endpoints

### Models

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/models` | List all models |
| GET | `/models/{name}` | Get model details |
| POST | `/models` | Register new model |
| PUT | `/models/{name}` | Update model |
| DELETE | `/models/{name}` | Delete model |
| GET | `/models/{name}/versions` | List model versions |
| GET | `/models/{name}/lineage` | Get model lineage |

### Data Contribution

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/contribute` | Submit data contribution |
| GET | `/contributions` | List contributions |
| GET | `/contributions/{id}` | Get contribution details |
| GET | `/contributions/{id}/status` | Check contribution status |

### Performance

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/metrics/{model}` | Get model metrics |
| GET | `/deltaone/{model}` | Check DeltaOne status |
| GET | `/deltaone/history` | Get DeltaOne history |
| POST | `/deltaone/webhook` | Configure webhook |

### Rewards

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/rewards` | List pending rewards |
| GET | `/rewards/{address}` | Get rewards by address |
| POST | `/rewards/claim` | Claim rewards |
| GET | `/rewards/history` | Get reward history |

### DSPy

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/dspy/signatures` | List available signatures |
| POST | `/dspy/execute` | Execute signature |
| POST | `/dspy/batch` | Batch execution |
| GET | `/dspy/results/{id}` | Get execution results |

## Quick Start Examples

### Register a Model

```bash
curl -X POST https://api.hokus.ai/v1/models \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sentiment-analyzer",
    "token_id": "SENT-001",
    "model_uri": "runs:/abc123/model",
    "benchmark_metric": "f1_score",
    "benchmark_value": "0.85"
  }'
```

### Submit Data

```bash
curl -X POST https://api.hokus.ai/v1/contribute \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "sentiment-analyzer",
    "data_url": "s3://bucket/data.json",
    "eth_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f5b4e1",
    "metadata": {
      "samples": 10000,
      "source": "customer_reviews"
    }
  }'
```

### Check DeltaOne

```bash
curl -X GET https://api.hokus.ai/v1/deltaone/sentiment-analyzer \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## SDK Support

Official SDKs are available for:

- [Python SDK](./python-sdk.md)
- [JavaScript/TypeScript SDK](./javascript-sdk.md)
- [Go SDK](./go-sdk.md)
- [Java SDK](./java-sdk.md)

## API Sections

Detailed documentation for each API section:

- [Model Management API](./models-api.md)
- [Data Contribution API](./contribution-api.md)
- [Performance Tracking API](./performance-api.md)
- [Rewards API](./rewards-api.md)
- [DSPy Execution API](./dspy-api.md)
- [Webhooks](./webhooks.md)
- [Error Codes](./error-codes.md)

## Need Help?

- Check our [API FAQ](./faq.md)
- Join our [Discord](https://discord.gg/hokusai) for support
- Email [api-support@hokus.ai](mailto:api-support@hokus.ai)