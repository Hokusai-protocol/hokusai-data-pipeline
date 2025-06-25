---
title: Your First Contribution
id: first-contribution
sidebar_label: First Contribution
sidebar_position: 3
---

# Your First Contribution

This guide walks you through submitting your first data contribution to improve a machine learning model using the Hokusai pipeline.

## Prerequisites

Before starting, ensure you have:
- ✅ [Installed the pipeline](./installation.md)
- ✅ [Run the quick start](./quick-start.md)
- ✅ An Ethereum wallet address for rewards
- ✅ Training data in a supported format

## Step 1: Prepare Your Data

### Supported Formats

The pipeline accepts data in three formats:

#### CSV Format (Recommended for beginners)
```csv
query,document,relevance
"What is deep learning?","Deep learning is a subset of machine learning...",1
"How to cook pasta?","Deep learning uses neural networks...",0
"Explain neural networks","Neural networks are computing systems...",1
```

#### JSON Format
```json
[
  {
    "query": "What is deep learning?",
    "document": "Deep learning is a subset of machine learning...",
    "relevance": 1
  },
  {
    "query": "How to cook pasta?",
    "document": "Deep learning uses neural networks...",
    "relevance": 0
  }
]
```

#### Parquet Format
For large datasets (>100MB), use Parquet for better performance.

### Data Quality Guidelines

Your data should:
- ✅ Be relevant to the model's domain
- ✅ Have accurate labels
- ✅ Not contain duplicate entries
- ✅ Pass PII detection checks
- ✅ Be at least 100 samples (recommended: 1000+)

## Step 2: Validate Your Data

Before submission, validate your data:

```bash
# Basic validation
python -m src.cli.validate_data \
    --input-file=my_contribution.csv \
    --check-pii \
    --check-duplicates
```

Expected output:
```
✓ File format: Valid CSV
✓ Required columns: Present
✓ Data types: Correct
✓ PII check: No sensitive data detected
✓ Duplicates: 0 found
✓ Sample count: 1,234 rows

Data validation passed! Ready for contribution.
```

### Fix Common Issues

#### Missing Columns
```bash
# Error: Missing required column 'relevance'
# Fix: Ensure your CSV has all required columns: query, document, relevance
```

#### Invalid Labels
```bash
# Error: Invalid relevance values found
# Fix: Relevance must be 0 or 1 (binary classification)
```

## Step 3: Preview Expected Improvement

Get an estimate of how your data will improve the model:

```bash
python -m src.preview.preview_improvement \
    --baseline-model=models/current_baseline.pkl \
    --contributed-data=my_contribution.csv \
    --sample-size=500
```

Output:
```
Preview Results (Non-binding Estimate):
- Baseline Accuracy: 0.854
- Estimated New Accuracy: 0.881
- Expected Improvement: +2.7%
- Estimated Reward Multiplier: 1.27x

Note: Actual results may vary. This is a preview only.
```

## Step 4: Set Your Contributor Information

Configure your wallet address for rewards:

```bash
# Set via environment variable
export CONTRIBUTOR_WALLET_ADDRESS="0x742d35Cc6634C0532925a3b844Bc9e7595f6234"

# Or pass directly to pipeline
--contributor-address="0x742d35Cc6634C0532925a3b844Bc9e7595f6234"
```

## Step 5: Run the Full Pipeline

Submit your contribution:

```bash
python -m src.pipeline.hokusai_pipeline run \
    --baseline-model-path=models/current_baseline.pkl \
    --contributed-data=my_contribution.csv \
    --contributor-address="0x742d35Cc6634C0532925a3b844Bc9e7595f6234" \
    --experiment-name="first-contribution" \
    --output-dir=./my-first-contribution
```

### Monitor Progress

The pipeline will show progress:
```
[Step 1/7] Loading baseline model... ✓
[Step 2/7] Validating contributed data... ✓
[Step 3/7] Integrating datasets... ✓
[Step 4/7] Training improved model... ✓
[Step 5/7] Evaluating models... ✓
[Step 6/7] Computing performance delta... ✓
[Step 7/7] Generating attestation... ✓

Pipeline completed successfully!
```

## Step 6: Review Your Results

### Check the Attestation Output

```bash
# View your attestation
cat my-first-contribution/deltaone_output_*.json | jq '.'
```

Key sections to review:
```json
{
  "delta_computation": {
    "metric_deltas": {
      "accuracy": {
        "baseline_value": 0.854,
        "new_value": 0.881,
        "absolute_delta": 0.027,
        "improvement": true
      }
    }
  },
  "contributor_attribution": {
    "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f6234",
    "contribution_hash": "sha256:abc123...",
    "contributed_samples": 1234
  }
}
```

### View in MLFlow UI

```bash
# Start MLFlow
mlflow ui

# Navigate to http://localhost:5000
# Find your experiment: "first-contribution"
```

## Step 7: Understanding Your Rewards

### Reward Calculation

Your rewards are based on:
1. **Performance Improvement**: How much your data improved the model
2. **Data Quality**: Uniqueness and relevance of your contribution
3. **Data Quantity**: Number of high-quality samples

### Attestation for On-Chain Rewards

The attestation file serves as proof of your contribution:
- Contains cryptographic hashes
- Verifiable performance metrics
- Ready for ZK-proof generation
- Enables trustless reward distribution

## Next Steps

### Submit More Data

Now that you understand the process:

1. **Collect More Data**: Focus on edge cases the model struggles with
2. **Improve Quality**: Higher quality data yields better rewards
3. **Collaborate**: Team up with others for larger contributions

### Advanced Features

- [Multi-Contributor Submissions](../tutorials/multi-contributor.md)
- [HuggingFace Dataset Integration](../tutorials/huggingface-integration.md)
- [Custom Model Types](../ml-platform/core-concepts.md)

### Track Your Contributions

```bash
# List all your contributions
python -m src.cli.list_contributions \
    --wallet-address="0x742d35Cc6634C0532925a3b844Bc9e7595f6234"

# Get total impact
python -m src.cli.contributor_stats \
    --wallet-address="0x742d35Cc6634C0532925a3b844Bc9e7595f6234"
```

## Troubleshooting

### Common Issues

#### "Baseline model not found"
```bash
# Download the latest baseline
python -m src.cli.download_baseline \
    --model-type=text-classification \
    --output-path=models/
```

#### "Insufficient improvement"
- Your data might be too similar to existing training data
- Try focusing on areas where the model performs poorly
- Use the preview tool to test different data subsets

#### "Data validation failed"
- Check the validation error details
- Ensure data format matches examples exactly
- Remove any corrupted or malformed entries

### Getting Help

If you encounter issues:
1. Check the detailed logs in `outputs/pipeline.log`
2. Join our [Discord](https://discord.gg/hokusai) #data-contributors channel
3. Review [FAQ](../reference/glossary.md#faq)

## Best Practices

### 1. Data Quality Over Quantity
- 100 high-quality samples > 1000 poor samples
- Focus on edge cases and errors
- Ensure accurate labeling

### 2. Privacy and Ethics
- Never include personal information
- Respect data licensing
- Follow ethical AI guidelines

### 3. Iterative Improvement
- Start small and iterate
- Use preview mode to test
- Learn from attestation feedback

## Summary

You've successfully:
- ✅ Prepared and validated training data
- ✅ Submitted your first contribution
- ✅ Generated an attestation for rewards
- ✅ Learned to track your impact

Welcome to the Hokusai contributor community! Your data is helping build better AI models while earning you rewards.

---

**Ready for more?** Check out our [tutorials](../tutorials/basic-workflow.md) for advanced contribution strategies.