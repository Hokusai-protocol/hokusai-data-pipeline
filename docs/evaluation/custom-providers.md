# Custom Providers

This guide shows how to implement and register custom HEK evaluation providers.

Related pages:
- [Concepts](./concepts.md)
- [API Reference](./api-reference.md)

## When to use a custom provider

Use a custom provider when:
- Your eval system is external to MLflow-native evaluation
- You need provider-specific execution details
- You still want consistent run IDs and HEM conversion

## Provider contract

A provider must satisfy `EvalAdapter`:

```python
from src.evaluation import EvalAdapter

class MyAdapter:
    def run(self, eval_spec: str, model_ref: str) -> str:
        ...
```

## Register and execute

```python
from src.evaluation import register_adapter, get_adapter

register_adapter("my_provider", MyAdapter())
run_id = get_adapter("my_provider").run(eval_spec="my-eval-v1", model_ref="models:/my-model")
print(run_id)
```

## Complete working example

```python
import json
import tempfile
from pathlib import Path

import mlflow

from src.evaluation import register_adapter, get_adapter, clear_adapters
from src.evaluation.manifest import create_hem_from_mlflow_run, log_hem_to_mlflow


class LocalJsonEvalAdapter:
    """Adapter that reads metrics from a local JSON eval spec and logs them to MLflow."""

    def __init__(self, tracking_uri: str = "http://localhost:5000") -> None:
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment("hek-custom-provider")

    def run(self, eval_spec: str, model_ref: str) -> str:
        payload = json.loads(Path(eval_spec).read_text(encoding="utf-8"))
        metrics = payload["metrics"]

        with mlflow.start_run(run_name="local-json-eval") as run:
            mlflow.set_tag("hokusai.eval_id", payload.get("eval_id", "custom-eval"))
            mlflow.set_tag("hokusai.model_id", model_ref)
            mlflow.set_tag("hokusai.primary_metric", payload.get("primary_metric", "accuracy"))
            mlflow.set_tag("hokusai.dataset.id", payload["dataset"]["id"])
            mlflow.set_tag("hokusai.dataset.hash", payload["dataset"]["hash"])
            mlflow.set_tag("hokusai.dataset.num_samples", str(payload["dataset"]["num_samples"]))

            for name, value in metrics.items():
                mlflow.log_metric(name, float(value))

            return run.info.run_id


# Create input spec
spec = {
    "eval_id": "json-eval-v1",
    "primary_metric": "accuracy",
    "dataset": {
        "id": "support-intents-v1",
        "hash": "sha256:" + "b" * 64,
        "num_samples": 1200,
    },
    "metrics": {
        "accuracy": 0.91,
        "f1": 0.89,
    },
}

with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
    json.dump(spec, handle)
    spec_path = handle.name

# Register + run
clear_adapters()
register_adapter("local_json", LocalJsonEvalAdapter())
run_id = get_adapter("local_json").run(eval_spec=spec_path, model_ref="ticket-classifier")

# Convert to HEM
manifest = create_hem_from_mlflow_run(run_id)
log_hem_to_mlflow(manifest, run_id=run_id)
print(run_id)
print(manifest.compute_hash())
```

## Best practices

- Keep adapter `run(...)` idempotent when possible.
- Always set `hokusai.eval_id`, `hokusai.dataset.id`, `hokusai.dataset.hash`, and `hokusai.primary_metric`.
- Emit numeric metrics only for values you want compared.
- Validate dataset hash format as `sha256:<64 lowercase hex>`.

## Troubleshooting

See [Troubleshooting](./troubleshooting.md) for adapter registration and missing-tag failures.
