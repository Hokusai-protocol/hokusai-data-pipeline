# Dataset Management for HEK

This guide covers evaluation dataset practices for reliable HEK and DeltaOne outcomes.

Related pages:
- [Quick Start](./quickstart.md)
- [Cost Optimization](./cost-optimization.md)

## Required metadata for comparability

To support HEM and DeltaOne comparisons, log:
- `hokusai.dataset.id`
- `hokusai.dataset.hash`
- `hokusai.dataset.num_samples`
- `hokusai.primary_metric`

## Recommended dataset format

For MLflow GenAI evaluation use a table-like dataset with clear fields:
- `inputs`
- `outputs` (model output)
- `expectations` (ground truth or target)
- Optional metadata columns (`language`, `segment`, `difficulty`)

Example CSV header:

```text
inputs,expectations,segment,difficulty
"User asks refund policy","Refunds are accepted within 30 days",billing,easy
```

## Hashing and versioning

Use content-addressable hashes for dataset consistency.

```python
import hashlib
from pathlib import Path

def sha256_file(path: str) -> str:
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return f"sha256:{digest}"
```

Store dataset version + hash in tags/params.

## Size recommendations

- Local iteration: 50-200 rows
- Pre-merge CI: 200-2,000 rows
- Release gate: 1,000+ rows for stable confidence intervals

If using `DeltaOneEvaluator`, keep `num_samples >= min_examples` (default `800`).

## Sensitive data handling

- Remove direct identifiers before evaluation.
- Keep secrets out of eval specs and tags.
- Avoid logging raw PII in prompt text or artifacts.
- Use private storage for sensitive datasets.

## Quality checks before running

- No null `inputs`/`expectations`
- Deterministic split strategy
- Balanced class distribution (for classification)
- Duplicate and leakage checks
- Stable dataset hash generated after final preprocessing

## Example metadata logging

```python
import mlflow

mlflow.set_tag("hokusai.dataset.id", "customer-support-v3")
mlflow.set_tag("hokusai.dataset.hash", "sha256:" + "c" * 64)
mlflow.set_tag("hokusai.dataset.num_samples", "1536")
mlflow.set_tag("hokusai.primary_metric", "accuracy")
```
