---
title: Data Contribution Overview
id: data-contribution-overview
sidebar_label: Overview
sidebar_position: 1
---

# Data Contribution Overview

## Introduction

Contributing data to the Hokusai pipeline is the primary way to improve machine learning models and earn attribution rewards. This guide explains the process, requirements, and best practices for data contribution.

## What is Data Contribution?

Data contribution involves providing high-quality datasets that can be used to:
- Fine-tune existing models
- Improve model accuracy and performance
- Expand model capabilities to new domains
- Enhance model robustness

Contributors receive:
- Attribution in the pipeline output
- Verifiable proof of contribution
- Potential rewards based on improvement metrics

## Contribution Process

```mermaid
graph LR
    A[Prepare Data] --> B[Validate Format]
    B --> C[Submit to Pipeline]
    C --> D[Processing]
    D --> E[Model Training]
    E --> F[Evaluation]
    F --> G[Attribution Output]
```

## Supported Data Types

### 1. Query-Document Pairs
Most common format for information retrieval models:

```csv
query_id,query,document_id,relevance_label
q001,"machine learning basics",doc123,1
q002,"python programming",doc456,0
```

### 2. Classification Data
For classification model improvements:

```json
{
  "samples": [
    {
      "id": "sample_001",
      "text": "This product is amazing!",
      "label": "positive",
      "confidence": 0.95
    }
  ]
}
```

### 3. Structured Datasets
For complex model training:

```parquet
# Parquet format with schema
├── features (array<float>)
├── labels (string)
├── metadata (struct)
└── contributor_id (string)
```

## Data Quality Requirements

### Minimum Requirements

1. **Size**: Minimum 100 samples
2. **Format**: Valid CSV, JSON, or Parquet
3. **Schema**: Must match expected structure
4. **Encoding**: UTF-8 for text data
5. **Completeness**: No critical missing values

### Quality Metrics

The pipeline evaluates data quality based on:

| Metric | Description | Threshold |
|--------|-------------|-----------|
| Completeness | Non-null value percentage | > 95% |
| Uniqueness | Unique sample percentage | > 80% |
| Consistency | Format consistency | 100% |
| Validity | Schema compliance | 100% |

## Contributor Attribution

### ETH Wallet Integration

Contributors must provide an Ethereum wallet address for attribution:

```python
# In your data manifest
{
  "contributor_info": {
    "contributor_id": "unique_id_123",
    "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
    "contribution_date": "2024-01-15T10:30:00Z"
  }
}
```

### Attribution Weighting

Attribution is calculated based on:
1. Data volume (number of samples)
2. Data quality score
3. Model improvement delta
4. Uniqueness of contribution

## Privacy and Compliance

### PII Handling

The pipeline automatically:
- Detects potential PII fields
- Hashes sensitive identifiers
- Removes direct identifiers
- Logs privacy actions

### Data Rights

By contributing data, you confirm:
- You have rights to share the data
- Data doesn't violate privacy laws
- Content is appropriately licensed
- No proprietary information is included

## Quick Start Example

### 1. Prepare Your Data

Create a CSV file with your contributions:

```csv
query_id,query,document_id,relevance
custom_001,"How to use Hokusai pipeline?",doc_hokusai_guide,1
custom_002,"What is machine learning?",doc_ml_intro,1
custom_003,"Best pizza recipe",doc_pizza,0
```

### 2. Add Contributor Information

Create a manifest file:

```json
{
  "contributor_id": "contributor_alice",
  "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
  "data_description": "Technology documentation queries",
  "data_source": "Manual curation",
  "license": "CC-BY-4.0"
}
```

### 3. Validate Your Data

```bash
# Validate before submission
python -m src.utils.validate_contribution \
    --data=my_contribution.csv \
    --manifest=manifest.json
```

### 4. Submit to Pipeline

```bash
# Run pipeline with your data
python -m src.pipeline.hokusai_pipeline run \
    --contributed-data=my_contribution.csv \
    --contributor-manifest=manifest.json \
    --output-dir=./outputs
```

## Best Practices

### 1. Data Preparation

- **Clean your data**: Remove duplicates and errors
- **Consistent formatting**: Use standard encodings
- **Meaningful IDs**: Use descriptive identifiers
- **Document sources**: Track data provenance

### 2. Quality Optimization

- **Balance labels**: Avoid skewed distributions
- **Diverse examples**: Cover edge cases
- **Validate early**: Test with small samples first
- **Iterate**: Refine based on quality scores

### 3. Security

- **Remove PII**: Clean personal information
- **Use hashing**: For any identifiers
- **Secure storage**: Encrypt sensitive data
- **Access control**: Limit data access

## Common Issues

### Issue: Schema Validation Fails

```
Error: Column 'query_id' not found
```

**Solution**: Ensure your data matches the expected schema exactly

### Issue: Data Quality Too Low

```
Warning: Data quality score 0.65 below threshold 0.80
```

**Solution**: Review and clean your data, remove duplicates

### Issue: Wallet Address Invalid

```
Error: Invalid Ethereum address format
```

**Solution**: Verify wallet address starts with '0x' and has 40 hex characters

## Advanced Topics

### Multi-Contributor Datasets

For collaborative contributions:

```json
{
  "contributors": [
    {
      "id": "alice",
      "wallet_address": "0xAlice...",
      "weight": 0.6
    },
    {
      "id": "bob",
      "wallet_address": "0xBob...",
      "weight": 0.4
    }
  ]
}
```

### Incremental Contributions

Submit data in batches:

```bash
# First batch
python -m src.pipeline.hokusai_pipeline run \
    --contributed-data=batch1.csv \
    --incremental-mode=true

# Additional batch
python -m src.pipeline.hokusai_pipeline run \
    --contributed-data=batch2.csv \
    --incremental-mode=true \
    --previous-run-id=run_123
```

## Next Steps

- [Data Formats](./data-formats.md) - Detailed format specifications
- [Validation Rules](./validation-rules.md) - Complete validation guide
- [ETH Wallet Setup](./eth-wallet-setup.md) - Wallet configuration
- [Submission Process](./submission-process.md) - Step-by-step submission