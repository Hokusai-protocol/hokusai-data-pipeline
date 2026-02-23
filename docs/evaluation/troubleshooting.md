# HEK Troubleshooting

This page lists common HEK evaluation failures and fixes.

Related pages:
- [Quick Start](./quickstart.md)
- [Migration Guide](./migration-guide.md)

## 1. `ImportError: mlflow is required ...`

Cause:
- ML dependencies are not installed.

Fix:

```bash
pip install -e "./hokusai-ml-platform[ml]"
```

## 2. `ValueError: Missing dataset hash ...`

Cause:
- Run is missing required dataset metadata.

Fix:

```python
mlflow.set_tag("hokusai.dataset.id", "my-dataset")
mlflow.set_tag("hokusai.dataset.hash", "sha256:" + "e" * 64)
mlflow.set_tag("hokusai.dataset.num_samples", "1000")
```

## 3. `Dataset hash must be exact 'sha256:<64 lowercase hex>' format`

Cause:
- Hash format is invalid.

Fix:
- Ensure lowercase hex and `sha256:` prefix.
- Hash post-processed dataset files, not raw inputs.

## 4. `delta_below_threshold` or `not_statistically_significant`

Cause:
- Candidate does not meet DeltaOne policy.

Fix:
- Increase evaluation sample size.
- Verify candidate/baseline compare same dataset hash.
- Use realistic threshold for your metric stability.

## 5. Cooldown rejection (`cooldown_active...`)

Cause:
- Previous DeltaOne check for same model/dataset happened recently.

Fix:
- Wait for cooldown window.
- For test environments, set `cooldown_hours=0`.

## 6. `Adapter 'name' is already registered`

Cause:
- Duplicate adapter registration in the same process.

Fix:

```python
from src.evaluation import clear_adapters
clear_adapters()
```

## 7. `oaieval` not found

Cause:
- OpenAI Evals CLI not installed for `OpenAIEvalsAdapter`.

Fix:

```bash
pip install openai-evals
```

## 8. DeepEval judge lookup unavailable

Cause:
- Current MLflow runtime does not expose `mlflow.genai.get_judge`.

Fix:

```python
from src.evaluation.judges import is_deepeval_judge_api_available

if not is_deepeval_judge_api_available():
    # fallback to create_*_judge helpers
    pass
```

## 9. CI fails with cost cap exceeded

Cause:
- Estimated or runtime cost is above configured `--max-cost`.

Fix:
- Reduce sample size for PR checks.
- Reduce judge count/dimensions.
- Run with resume and deterministic seed.
