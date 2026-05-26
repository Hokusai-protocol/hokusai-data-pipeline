# Model 30 Serving

`POST /api/v1/models/30/predict` serves the registered MLflow Technical Task Router model through the public nested request contract `technical_task_router_inputs/v1`.

## Public Contract

Accepted `inputs` groups:

- `task` (required)
- `routing`
- `context`
- `workflow`
- `prediction`
- `outcome`
- `rubric`
- `metadata`

Top-level flat benchmark-row fields such as `schema_version`, `task_descriptor`, `allowed_models`, `selected_models`, and `max_cost_usd` are rejected with `422`. Those fields belong to the benchmark/evaluation row contract, not the live serving API.

## MLflow Configuration

Environment variables:

- `MODEL_30_MLFLOW_URI` defaults to `models:/Technical Task Router/1`
- `MLFLOW_TRACKING_URI` must point at the registry/tracking server
- Any auth token or mTLS environment expected by the deployed MLflow stack must also be present

The API startup path already configures MLflow mTLS behavior in `src/api/main.py` through `src/utils/mlflow_config.configure_internal_mtls()`. This serving path relies on that shared setup and does not duplicate transport configuration.

## Adapter Behavior

The serving path validates the nested request, maps it into a one-row pandas feature frame, calls `mlflow.pyfunc.load_model(model_uri).predict(...)`, then normalizes raw output into:

```json
{
  "selected_model": "deep-coder-v2",
  "selected_models": ["deep-coder-v2"],
  "confidence": 0.91,
  "rationale": "Preferred high quality route",
  "estimated_cost_usd": 0.42
}
```

Normalization accepts common aliases from the model output:

- `model`, `selected`, `prediction` -> `selected_model`
- `models` -> `selected_models`
- `score`, `probability` -> `confidence`
- `cost`, `estimated_cost` -> `estimated_cost_usd`

There is no deterministic fallback when MLflow is configured. Load, predict, or normalization failures return `503` with a `Model 30 MLflow inference failed` prefix.

## Response Metadata

Model 30 responses include:

- `metadata.model_uri`
- `metadata.model_version`
- `metadata.schema`
- `metadata.request_id`

`request_id` matches `inference_log_id` so callers can correlate the public response with persisted inference logs.

## Smoke Test

Unit and targeted endpoint verification:

```bash
ruff check src/api/endpoints/model_30_adapter.py src/api/endpoints/model_serving.py src/api/schemas/technical_task_router_inputs.py tests/unit/test_model_30_adapter.py tests/unit/test_model_serving.py
pytest tests/unit/test_model_30_adapter.py tests/unit/test_model_serving.py tests/unit/test_model_serving_auth.py -v
```

Optional live registry smoke test:

```bash
MODEL_30_INTEGRATION_TEST=1 pytest tests/integration/test_model_30_mlflow_serving.py -v
```

That integration test requires `MLFLOW_TRACKING_URI` and any registry credentials/certs needed by the environment.

## Follow-Up

After validating `Technical Task Router` version `1`, set the registered model alias `production` and switch `MODEL_30_MLFLOW_URI` to `models:/Technical Task Router@production` when the deployment path is ready for alias-based promotion.
