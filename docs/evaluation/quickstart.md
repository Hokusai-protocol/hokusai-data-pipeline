# HEK Quick Start (10 Minutes)

This guide runs a first HEK evaluation using MLflow 3.9.0-compatible patterns.

Related pages:
- [Concepts](./concepts.md)
- [Migration Guide](./migration-guide.md)

## 1. Install

If you use the packaged SDK:

```bash
pip install "hokusai-sdk[ml]"
```

For this repository layout, install the local SDK package:

```bash
pip install -e "./hokusai-ml-platform[ml]"
```

## 2. Configure MLflow

```bash
export MLFLOW_TRACKING_URI="http://localhost:5000"
# Optional when your MLflow endpoint requires auth
# export MLFLOW_TRACKING_TOKEN="<your-token>"
```

## 3. Run a minimal evaluation

```python
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

import mlflow
from src.modules.evaluation import ModelEvaluator

# 1) Train a small model
X = pd.DataFrame({"x1": [0, 0, 1, 1], "x2": [0, 1, 0, 1]})
y = pd.Series([0, 0, 1, 1])
model = LogisticRegression().fit(X, y)

# 2) Start run and attach HEK tags
mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("hek-quickstart")

with mlflow.start_run(run_name="quickstart-eval") as run:
    mlflow.set_tag("hokusai.eval_id", "quickstart-v1")
    mlflow.set_tag("hokusai.model_id", "demo-model")
    mlflow.set_tag("hokusai.primary_metric", "accuracy")
    mlflow.set_tag("hokusai.dataset.id", "toy-dataset")
    mlflow.set_tag("hokusai.dataset.hash", "sha256:" + "a" * 64)
    mlflow.set_tag("hokusai.dataset.num_samples", str(len(X)))

    evaluator = ModelEvaluator(metrics=["accuracy", "precision", "recall", "f1", "auroc"])
    metrics = evaluator.evaluate_sklearn_model(model, X, y)

    for name, value in metrics.items():
        if value is not None:
            mlflow.log_metric(name, float(value))

    print("run_id:", run.info.run_id)
    print("metrics:", metrics)
```

## 4. Create and log HEM

```python
from src.evaluation.manifest import create_hem_from_mlflow_run, log_hem_to_mlflow

run_id = "<paste-run-id>"
manifest = create_hem_from_mlflow_run(run_id)
log_hem_to_mlflow(manifest, run_id=run_id)

print(manifest.to_json())
```

## 5. Optional: Evaluate DeltaOne against baseline

```python
from src.evaluation.deltaone_evaluator import DeltaOneEvaluator

evaluator = DeltaOneEvaluator(cooldown_hours=0, min_examples=4, delta_threshold_pp=1.0)
decision = evaluator.evaluate(
    mlflow_run_id="<candidate-run-id>",
    baseline_mlflow_run_id="<baseline-run-id>",
)
print(decision)
```

## 6. Optional: Create an LLM judge

```python
from src.evaluation.judges import JudgeConfig, create_generation_judge

judge = create_generation_judge(
    metrics=["fluency", "relevance", "faithfulness"],
    config=JudgeConfig(model="anthropic:/claude-opus-4-1-20250805"),
)
print(judge)
```

Next:
- [API Reference](./api-reference.md)
- [Custom Providers](./custom-providers.md)
- [Dataset Management](./dataset-management.md)
