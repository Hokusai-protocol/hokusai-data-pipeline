# Migration Guide: Legacy Evals to HEK + MLflow 3.9.0

This guide has two migration tracks:
1. Ad-hoc scripts -> HEK
2. MLflow pre-3.9 patterns -> MLflow 3.9.0-compatible patterns

Related pages:
- [Quick Start](./quickstart.md)
- [API Reference](./api-reference.md)

## Fast path chooser

- If you have handwritten eval scripts with inconsistent outputs: start at [Track A](#track-a-ad-hoc-eval-scripts-to-hek)
- If your code already uses MLflow but references deprecated APIs: start at [Track B](#track-b-mlflow-breaking-changes)

## Track A: Ad-hoc eval scripts to HEK

### Before

```python
# ad_hoc_eval.py
results = run_custom_eval(model, dataset)
print(results["accuracy"])  # No standardized logging or manifest
```

### After

```python
import mlflow

from src.modules.evaluation import ModelEvaluator
from src.evaluation.manifest import create_hem_from_mlflow_run, log_hem_to_mlflow

mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("hek-migration")

with mlflow.start_run() as run:
    mlflow.set_tag("hokusai.eval_id", "intent-eval-v2")
    mlflow.set_tag("hokusai.model_id", "intent-model")
    mlflow.set_tag("hokusai.primary_metric", "accuracy")
    mlflow.set_tag("hokusai.dataset.id", "intent-dataset-v2")
    mlflow.set_tag("hokusai.dataset.hash", "sha256:" + "d" * 64)
    mlflow.set_tag("hokusai.dataset.num_samples", "1200")

    metrics = ModelEvaluator(metrics=["accuracy", "f1"]).evaluate_sklearn_model(model, X, y)
    for k, v in metrics.items():
        if v is not None:
            mlflow.log_metric(k, v)

manifest = create_hem_from_mlflow_run(run.info.run_id)
log_hem_to_mlflow(manifest, run_id=run.info.run_id)
```

## Track B: MLflow breaking changes

### 1. Legacy custom metric argument -> `extra_metrics`

Before:

```python
results = mlflow.evaluate(
    model=model,
    data=X_test,
    targets=y_test,
    legacy_custom_metric_arg=[my_metric],
)
```

After:

```python
results = mlflow.evaluate(
    model=model,
    data=X_test,
    targets=y_test,
    extra_metrics=[my_metric],
)
```

### 2. Model stages -> aliases

Before:

```python
model = mlflow.pyfunc.load_model("models:/my-model/Production")
```

After:

```python
client = mlflow.tracking.MlflowClient()
version = client.get_model_version_by_alias("my-model", "production")
model = mlflow.pyfunc.load_model(f"models:/my-model/{version.version}")
```

### 3. MLflow Recipes module removal

Before:

```python
from mlflow import recipes
recipes.run("classification")
```

After:

```python
# Replace legacy recipe orchestration with explicit training/evaluation pipeline steps
# and call mlflow.evaluate directly in your workflow.
```

## Judge migration notes

### `make_judge()` usage

```python
from src.evaluation.judges import JudgeConfig, create_generation_judge

judge = create_generation_judge(
    metrics=["fluency", "relevance"],
    config=JudgeConfig(model="anthropic:/claude-opus-4-1-20250805"),
)
```

### `get_judge()` availability

```python
from src.evaluation.judges import is_deepeval_judge_api_available, get_faithfulness_judge

if is_deepeval_judge_api_available():
    judge = get_faithfulness_judge()
else:
    judge = None  # fallback to make_judge-based template
```

## Migration checklist

- Replace all legacy custom metric argument usage with `extra_metrics`
- Replace stage-based registry access with aliases
- Remove legacy MLflow Recipes imports
- Add required HEK tags for dataset + primary metric
- Generate and log HEM manifests
- Add DeltaOne checks where promotion gates are required
