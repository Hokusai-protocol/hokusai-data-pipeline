# Dry Run Mode

The pipeline supports dry-run mode for testing without real data or models.

## Activation Methods

### Command Line Flag
```bash
PYTHONPATH=. python -m src.pipeline.hokusai_pipeline run \
    --dry-run \
    --contributed-data=data/test_fixtures/test_queries.csv \
    --output-dir=./outputs
```

### Environment Variable
```bash
export HOKUSAI_TEST_MODE=true
PYTHONPATH=. python -m src.pipeline.hokusai_pipeline run \
    --contributed-data=data/test_fixtures/test_queries.csv
```

## What Happens in Dry-Run Mode

1. **Mock Baseline Model**: Creates synthetic baseline with realistic metrics
2. **Mock Data Generation**: Generates deterministic datasets matching schema
3. **Simulated Training**: Mock training with plausible improvements
4. **Real Evaluation Logic**: Actual delta computation with mock data
5. **Complete Output**: Real DeltaOne JSON and attestation outputs

## Mock Data Characteristics

- **Deterministic**: Fixed seeds for reproducible results
- **Realistic Schema**: Proper columns and types
- **Configurable Size**: Appropriate dataset sizes
- **Edge Cases**: Various test scenarios

## Performance Requirements

- **Fast Execution**: < 2 minutes (typically ~7 seconds)
- **Full Coverage**: All pipeline steps execute
- **Valid Outputs**: Properly formatted JSON

## Example Output

```json
{
  "schema_version": "1.0",
  "delta_computation": {
    "delta_one_score": 0.0332,
    "metric_deltas": {
      "accuracy": {
        "baseline_value": 0.8545,
        "new_value": 0.8840,
        "absolute_delta": 0.0296,
        "relative_delta": 0.0346,
        "improvement": true
      }
    },
    "improved_metrics": ["accuracy", "precision", "recall", "f1", "auroc"],
    "degraded_metrics": []
  },
  "pipeline_metadata": {
    "dry_run": true,
    "run_id": "1749778320931703",
    "timestamp": "2025-06-13T01:32:07.220133"
  }
}
```

## Troubleshooting

### Common Issues

1. **MLflow Connection**: Check tracking URI accessibility
2. **File Permissions**: Ensure output directory is writable
3. **Module Import**: Use `PYTHONPATH=.` from project root
4. **Memory Issues**: Mock data is lightweight

### Debug Mode
```bash
export PIPELINE_LOG_LEVEL=DEBUG
PYTHONPATH=. python -m src.pipeline.hokusai_pipeline run --dry-run
```

## Environment Variables

- `HOKUSAI_TEST_MODE=true`: Enable test mode
- `PIPELINE_LOG_LEVEL=DEBUG`: Debug logging
- `RANDOM_SEED=42`: Deterministic seed (default)
- `MLFLOW_EXPERIMENT_NAME=test-experiment`: Separate experiment

## Integration with SDK

The SDK automatically handles dry-run mode:

```python
from hokusai.core import ModelRegistry

# This will use mock data if HOKUSAI_TEST_MODE=true
registry = ModelRegistry()
result = registry.register_baseline(
    model=mock_model,
    model_type="test",
    metadata={"test": True}
)
```