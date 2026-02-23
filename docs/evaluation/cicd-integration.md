# CI/CD Integration

This guide shows how to run HEK evaluations in CI and gate promotion on evaluation quality.

Related pages:
- [Quick Start](./quickstart.md)
- [Cost Optimization](./cost-optimization.md)
- [Troubleshooting](./troubleshooting.md)

## CI strategy

Use three levels:
- PR checks: small eval set, fast feedback
- Main branch checks: medium eval set, stronger confidence
- Release checks: full eval set + DeltaOne gate

## GitHub Actions example

```yaml
name: hek-eval
on:
  pull_request:
  push:
    branches: [main]

jobs:
  evaluate:
    runs-on: ubuntu-latest
    env:
      MLFLOW_TRACKING_URI: http://localhost:5000
      MLFLOW_TRACKING_TOKEN: ${{ secrets.MLFLOW_TRACKING_TOKEN }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install deps
        run: |
          pip install -e "./hokusai-ml-platform[ml]"
          pip install -r requirements-dev.txt
      - name: Run evaluation
        run: |
          python - <<'PY'
          import mlflow
          from src.cli.hoku_eval import _run_evaluation

          result = _run_evaluation(
              model_id="my-model",
              eval_spec="tests/fixtures/eval_dataset.json",
              provider=None,
              seed=42,
              temperature=None,
              max_cost=5.0,
              resume="auto",
              attest=True,
          )
          print(result)

          score = float(result["metrics"].get("accuracy", 0.0))
          if score < 0.85:
              raise SystemExit("accuracy gate failed")
          PY
```

## DeltaOne gating example

```python
from src.evaluation.deltaone_evaluator import DeltaOneEvaluator

decision = DeltaOneEvaluator(cooldown_hours=0).evaluate(
    mlflow_run_id="candidate-run-id",
    baseline_mlflow_run_id="baseline-run-id",
)
if not decision.accepted:
    raise SystemExit(f"DeltaOne gate failed: {decision.reason}")
```

## Recording history

Keep these artifacts/tags per run:
- `hem/manifest.json`
- Evaluation metrics and key thresholds
- `hoku_eval.status`
- Attestation hash when enabled (`--attest`)

## Recommended deployment policy

- Block deploy if evaluation run fails
- Block deploy if primary metric drops under policy threshold
- Block deploy if DeltaOne gate required and decision not accepted
- Alert on repeated judge failures or rising cost trend
