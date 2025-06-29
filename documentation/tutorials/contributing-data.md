---
id: contributing-data
title: Contributing Data for Rewards
sidebar_label: Contributing Data
sidebar_position: 2
---

# Contributing Data for Rewards

Learn how to contribute data to improve Hokusai models and earn token rewards when your contributions lead to DeltaOne achievements.

## Overview

Data contribution in Hokusai follows this flow:

1. **Prepare** your data according to model requirements
2. **Validate** data quality and format
3. **Submit** data with your ETH address
4. **Track** model improvements
5. **Receive** rewards if DeltaOne achieved

## Prerequisites

Before contributing data:

- ✅ Ethereum wallet address for receiving rewards
- ✅ Understanding of the target model's data requirements
- ✅ Data that complies with licensing requirements
- ✅ Hokusai CLI or Python SDK installed

## Step 1: Set Up Your Contributor Profile

### Create ETH Wallet

If you don't have an Ethereum wallet:

```python
from eth_account import Account

# Generate new wallet
account = Account.create()
print(f"Address: {account.address}")
print(f"Private Key: {account.privateKey.hex()}")
# ⚠️ Save your private key securely!
```

### Register as Contributor

```python
from hokusai.contributors import ContributorRegistry

registry = ContributorRegistry()

# Register your contributor profile
contributor = registry.register(
    eth_address="0x742d35Cc6634C0532925a3b844Bc9e7595f5b4e1",
    name="Alice Smith",  # Optional
    email="alice@example.com"  # Optional
)

print(f"Contributor ID: {contributor.id}")
```

## Step 2: Understand Data Requirements

### Check Model Requirements

```python
from hokusai.core import ModelRegistry

registry = ModelRegistry()

# Get model's data requirements
model_info = registry.get_model_info("sentiment-analyzer")
print(f"Data format: {model_info.data_requirements.format}")
print(f"Required fields: {model_info.data_requirements.fields}")
print(f"Min samples: {model_info.data_requirements.min_samples}")
```

### Common Data Formats

#### Text Classification Data
```json
{
  "samples": [
    {"text": "This product is amazing!", "label": "positive"},
    {"text": "Terrible experience.", "label": "negative"},
    {"text": "It's okay, nothing special.", "label": "neutral"}
  ]
}
```

#### Image Classification Data
```json
{
  "samples": [
    {"image_path": "images/cat_001.jpg", "label": "cat"},
    {"image_path": "images/dog_001.jpg", "label": "dog"}
  ],
  "metadata": {
    "image_format": "JPEG",
    "resolution": "224x224"
  }
}
```

#### Tabular Data
```csv
feature1,feature2,feature3,target
0.5,1.2,3.4,1
0.7,1.5,3.1,0
0.6,1.3,3.3,1
```

## Step 3: Prepare Your Data

### Data Validation

```python
from hokusai.data import DataValidator

validator = DataValidator()

# Validate your data
validation_result = validator.validate(
    data_path="my_contribution.csv",
    model_name="customer-churn-predictor"
)

if validation_result.is_valid:
    print("✅ Data is valid!")
else:
    print("❌ Validation errors:")
    for error in validation_result.errors:
        print(f"  - {error}")
```

### Data Privacy and PII

Automatically detect and handle PII:

```python
from hokusai.data import PIIDetector, DataAnonymizer

# Check for PII
detector = PIIDetector()
pii_found = detector.scan("my_data.csv")

if pii_found:
    print("⚠️ PII detected! Anonymizing...")
    
    # Anonymize data
    anonymizer = DataAnonymizer()
    anonymizer.anonymize_file(
        input_path="my_data.csv",
        output_path="my_data_anonymized.csv",
        methods={
            "email": "hash",
            "phone": "remove",
            "name": "generalize"
        }
    )
```

### Data Quality Checks

```python
from hokusai.data import QualityChecker

checker = QualityChecker()

# Run quality checks
quality_report = checker.analyze("my_contribution.csv")

print(f"Completeness: {quality_report.completeness:.1%}")
print(f"Duplicates: {quality_report.duplicate_count}")
print(f"Outliers: {quality_report.outlier_count}")

# Get specific recommendations
for recommendation in quality_report.recommendations:
    print(f"📌 {recommendation}")
```

## Step 4: Submit Your Data

### Using Python SDK

```python
from hokusai.data import DataContributor
from hokusai.utils.eth_address_validator import validate_eth_address

# Initialize contributor
contributor = DataContributor(
    eth_address="0x742d35Cc6634C0532925a3b844Bc9e7595f5b4e1"
)

# Validate ETH address
if not validate_eth_address(contributor.eth_address):
    raise ValueError("Invalid ETH address")

# Submit data
submission = contributor.submit(
    model_name="sentiment-analyzer",
    data_path="sentiment_data.json",
    data_format="json",
    metadata={
        "source": "customer_reviews",
        "language": "en",
        "sample_count": 10000
    }
)

print(f"Submission ID: {submission.id}")
print(f"Data hash: {submission.data_hash}")
print(f"Status: {submission.status}")
```

### Using CLI

```bash
# Submit data via CLI
hokusai contribute \
  --model sentiment-analyzer \
  --data ./sentiment_data.json \
  --eth-address 0x742d35Cc6634C0532925a3b844Bc9e7595f5b4e1 \
  --format json

# With additional metadata
hokusai contribute \
  --model image-classifier \
  --data ./images/ \
  --eth-address 0x742d35Cc6634C0532925a3b844Bc9e7595f5b4e1 \
  --format images \
  --metadata source=mobile_app \
  --metadata quality=high_res
```

### Batch Submissions

For large datasets:

```python
from hokusai.data import BatchContributor

batch = BatchContributor(eth_address=your_address)

# Split large dataset
batch.prepare_chunks(
    data_path="large_dataset.csv",
    chunk_size=10000
)

# Submit in batches
submission_ids = batch.submit_all(
    model_name="big-model",
    parallel=True,
    progress_bar=True
)

print(f"Submitted {len(submission_ids)} chunks")
```

## Step 5: Track Your Contributions

### Monitor Status

```python
from hokusai.contributors import ContributionTracker

tracker = ContributionTracker(eth_address=your_address)

# Get all contributions
contributions = tracker.get_contributions()

for contrib in contributions:
    print(f"Model: {contrib.model_name}")
    print(f"Status: {contrib.status}")
    print(f"Submitted: {contrib.timestamp}")
    print(f"Data size: {contrib.sample_count}")
    print("---")
```

### Track Model Improvements

```python
# Track specific contribution impact
impact = tracker.get_contribution_impact(submission_id)

print(f"Model version before: {impact.baseline_version}")
print(f"Model version after: {impact.improved_version}")
print(f"Metric improvement: {impact.metric_delta:.3f}pp")
print(f"DeltaOne achieved: {impact.deltaone_achieved}")
```

### Real-time Notifications

```python
from hokusai.contributors import NotificationService

# Set up notifications
notifier = NotificationService()

notifier.subscribe(
    eth_address=your_address,
    events=["deltaone_achieved", "model_trained", "reward_distributed"],
    webhook_url="https://your-app.com/webhook"
)
```

## Step 6: Earn Rewards

### Understanding Rewards

Rewards are distributed when:
- ✅ Your data contribution is used in model training
- ✅ The improved model achieves DeltaOne (≥1pp improvement)
- ✅ The improvement is verified on-chain

### Check Reward Status

```python
from hokusai.rewards import RewardChecker

checker = RewardChecker()

# Check pending rewards
rewards = checker.get_pending_rewards(your_address)

for reward in rewards:
    print(f"Model: {reward.model_name}")
    print(f"Amount: {reward.token_amount} {reward.token_symbol}")
    print(f"Status: {reward.status}")
    print(f"Contribution: {reward.contribution_id}")
```

### Claim Rewards

```python
from hokusai.rewards import RewardClaimer

claimer = RewardClaimer(
    eth_address=your_address,
    private_key=your_private_key  # Required for transaction signing
)

# Claim all pending rewards
tx_hash = claimer.claim_all()
print(f"Claim transaction: {tx_hash}")

# Or claim specific reward
tx_hash = claimer.claim_reward(reward_id)
```

## Data Licensing

### HuggingFace Datasets

When using HuggingFace datasets:

```python
from hokusai.data import HuggingFaceImporter

importer = HuggingFaceImporter()

# Check license compatibility
dataset_info = importer.check_dataset("squad")
print(f"License: {dataset_info.license}")
print(f"Compatible: {dataset_info.is_compatible}")

if dataset_info.is_compatible:
    # Import and contribute
    data = importer.import_dataset(
        "squad",
        split="train",
        sample_size=1000
    )
    
    # Submit with license info
    contributor.submit(
        model_name="qa-model",
        data=data,
        metadata={
            "source": "huggingface/squad",
            "license": dataset_info.license
        }
    )
```

### License Compatibility Matrix

| Dataset License | Commercial Models | Open Source Models |
|----------------|-------------------|-------------------|
| MIT, Apache 2.0 | ✅ Allowed | ✅ Allowed |
| CC BY | ✅ Allowed | ✅ Allowed |
| CC BY-NC | ❌ Not Allowed | ✅ Allowed |
| GPL | ❌ Check Terms | ✅ Allowed |
| Proprietary | ❌ Not Allowed | ❌ Not Allowed |

## Best Practices

### 1. Data Quality Over Quantity

Focus on high-quality, relevant data:

```python
# Good: Diverse, balanced data
quality_data = {
    "positive": 1000,  # Balanced classes
    "negative": 980,
    "neutral": 1020
}

# Less valuable: Imbalanced data
poor_data = {
    "positive": 5000,  # Heavily imbalanced
    "negative": 100,
    "neutral": 50
}
```

### 2. Document Your Data

Always include metadata:

```python
metadata = {
    "collection_method": "web_scraping",
    "date_range": "2024-01-01 to 2024-12-31",
    "preprocessing": "lowercased, removed_urls",
    "annotation_method": "expert_labeled",
    "quality_score": "high"
}
```

### 3. Incremental Contributions

Make regular, smaller contributions:

```python
# Better: Regular contributions
for week_data in weekly_batches:
    contributor.submit(
        model_name="model",
        data=week_data,
        metadata={"week": week_number}
    )
    
# Less optimal: One huge contribution
contributor.submit(
    model_name="model",
    data=entire_year_data
)
```

## Troubleshooting

### Common Issues

**"Data validation failed"**
```python
# Check validation errors
result = validator.validate(data)
for error in result.errors:
    print(f"Field: {error.field}")
    print(f"Issue: {error.message}")
    print(f"Fix: {error.suggestion}")
```

**"Insufficient data quality"**
```python
# Improve data quality
from hokusai.data import DataEnhancer

enhancer = DataEnhancer()
enhanced_data = enhancer.enhance(
    data,
    methods=["deduplication", "outlier_removal", "normalization"]
)
```

**"ETH address not recognized"**
```python
# Ensure address is registered
from hokusai.contributors import ContributorRegistry

registry = ContributorRegistry()
if not registry.is_registered(eth_address):
    registry.register(eth_address)
```

## Next Steps

- 📚 [Data Format Guide](../guides/data-formats.md) - Detailed format specifications
- 🔍 [Quality Guidelines](../guides/data-quality.md) - Best practices for data quality
- 💰 [Reward System](../guides/reward-system.md) - How rewards are calculated
- 🛡️ [Security Guide](../guides/security.md) - Keeping your data and wallet secure