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

## Accepted Shapes

`inputs` must contain a nested `task` group with both `description` and `task_type`.

Minimal accepted payload (`data/test_fixtures/model_30_minimal_payload.json`):

```json
{
  "inputs": {
    "task": {
      "description": "Implement password reset flow",
      "task_type": "feature"
    }
  }
}
```

Curated accepted payload (`data/test_fixtures/model_30_curated_payload.json`):

```json
{
  "inputs": {
    "task": {
      "description": "Refactor billing webhook retry handling",
      "task_type": "refactor",
      "language": "python",
      "framework": "fastapi",
      "repo_type": "monorepo"
    },
    "routing": {
      "available_models": ["fast-coder-v1", "deep-coder-v2"],
      "preferred_models": ["deep-coder-v2"],
      "max_cost_usd": 0.5,
      "max_latency_seconds": 30,
      "prioritize_quality": true
    },
    "context": {
      "domain": "payments",
      "repo_size_bucket": "large",
      "requires_tests": true,
      "risk_level": "medium",
      "file_count": 6,
      "estimated_complexity": "medium",
      "security_sensitive": true
    },
    "workflow": {
      "surface": "wavemill",
      "stages": ["plan", "code", "review"],
      "execution_environment": "ci",
      "human_review_required": true
    },
    "prediction": {
      "expected_duration_seconds": 1800,
      "expected_cost_usd": 0.45,
      "expected_success_probability": 0.8
    },
    "outcome": {
      "completed_successfully": false,
      "actual_cost_usd": 0.0,
      "actual_time_seconds": 0.0,
      "retry_count": 0,
      "intervention_required": false,
      "selected_model": "deep-coder-v2"
    },
    "rubric": {
      "quality_score": 0.9,
      "correctness_score": 0.85,
      "human_rating": "strong",
      "benchmark_passed": true
    },
    "metadata": {
      "external_task_id": "task-123",
      "run_id": "run-456",
      "integration_version": "2026.05",
      "idempotency_key": "idem-789"
    }
  }
}
```

## Rejected Shapes

Flat benchmark-row payloads are rejected because `TechnicalTaskRouterInputs` uses `extra="forbid"` and requires `task`.

Rejected benchmark/evaluation row shape:

```json
{
  "inputs": {
    "schema_version": "technical_task_router_row/v1",
    "task_descriptor": {"task_type": "feature"},
    "allowed_models": ["fast-coder-v1"],
    "max_cost_usd": 0.5
  }
}
```

Expected validation behavior:

- `Extra inputs are not permitted` for flat row fields such as `schema_version`, `task_descriptor`, and `allowed_models`
- `Field required` for missing `task`

This is the benchmark row contract, not the public serving API contract.

Rejected missing-task shape:

```json
{
  "inputs": {
    "routing": {
      "max_cost_usd": 0.5
    }
  }
}
```

Expected validation behavior:

- `Field required` on `task`

## MLflow Configuration

Environment variables:

- `MODEL_30_MLFLOW_URI` defaults to `models:/Technical Task Router/4`
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

## Nested API To Router Feature Mapping

Model 30 is served from the nested public API contract, but its live prediction frame uses the Wavemill router feature schema it was trained on. `model_30_inputs_to_features()` delegates to `map_nested_to_router_features()` and emits only router input columns:

- Direct task/context/workflow fields: `task_type`, `language`, `framework`, `repo_type`, `domain`, `risk_level`, `requires_tests`, `security_sensitive`, `repo_size_bucket`, and `surface`
- Derived buckets: `description_length_bucket` from task description length and `files_touched_bucket` from `context.file_count`
- `complexity` from `context.estimated_complexity` when present, otherwise a description/file-count fallback
- Role availability arrays: `available_planner_models`, `available_coder_models`, and `available_reviewer_models` all use the sorted, deduped `routing.available_models` list because the nested API does not yet provide role annotations
- Description-derived booleans: `is_greenfield`, `is_migration`, `cross_service`, and `ui_heavy`

Live prediction inputs intentionally exclude target, outcome, and leakage fields such as selected models, actual cost/time, retry/intervention counts, and completed outcome fields.

## Response Metadata

Model 30 responses include:

- `metadata.model_uri`
- `metadata.model_version`
- `metadata.schema`
- `metadata.request_id`

`request_id` matches `inference_log_id` so callers can correlate the public response with persisted inference logs.

## Latency Tracing

Each `POST /api/v1/models/30/predict` request now emits exactly one structured `model_30_latency_trace` log record. The trace is keyed by `request_id`, includes the caller-provided `metadata.run_id` when present, and classifies the path as `warm` or `cold` based on whether the MLflow artifact was already cached in-process.

Trace fields:

- `event`: fixed to `model_30_latency_trace`
- `request_id`: public-safe request correlation id, also returned in the API response
- `run_id`: optional caller correlation id from `inputs.metadata.run_id`
- `path_type`: `warm` or `cold`
- `outcome`: `success`, `timeout`, `validation_error`, `http_error`, or `error`
- `dominant_phase`: largest contributor across the per-phase timings and the timeout boundary
- `total_ms`: sum of the non-overlapping model 30 phases below
- `request_validation_ms`
- `model_cache_lookup_ms`
- `artifact_load_ms`
- `preprocessor_setup_ms`
- `feature_transformation_ms`
- `model_inference_ms`
- `postprocessing_serialization_ms`
- `timeout_deadline_boundary_ms`

Use `dominant_phase` to identify where the request spent the most time. A cold request typically shows `artifact_load` dominating, while a warm request should shift time toward `model_inference` or upstream data-shaping phases. Timeout responses include `request_id` and `run_id` in the `504` body so the matching trace can be found without exposing request payload details.

Sample CloudWatch Logs Insights query:

```sql
fields @timestamp, request_id, run_id, path_type, outcome, dominant_phase, total_ms,
       request_validation_ms, model_cache_lookup_ms, artifact_load_ms,
       preprocessor_setup_ms, feature_transformation_ms, model_inference_ms,
       postprocessing_serialization_ms, timeout_deadline_boundary_ms
| filter event = "model_30_latency_trace"
| sort @timestamp desc
| limit 50
```

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

After validating `Technical Task Router` version `4`, set the registered model alias `production` and switch `MODEL_30_MLFLOW_URI` to `models:/Technical Task Router@production` when the deployment path is ready for alias-based promotion.

## Local Reproduction Harness

Use `scripts/diagnostics/reproduce_model_30_inference.py` to reproduce model 30 behavior outside FastAPI while still loading the configured MLflow artifact through `src.api.endpoints.model_30_adapter`.

Prerequisites:

- Set `MLFLOW_TRACKING_URI` plus any auth or mTLS environment the deployed service uses
- Pass `--model-uri` or set `MODEL_30_MLFLOW_URI`
- Install dev dependencies if you want RSS sampling via `psutil`; otherwise the script falls back to `resource.getrusage(...)`

Example:

```bash
python -m scripts.diagnostics.reproduce_model_30_inference \
  --model-uri 'models:/Technical Task Router/4' \
  --warm-iterations 5 \
  --output /tmp/model-30-report.json
```

Fixture locations:

- `data/test_fixtures/model_30_curated_payload.json`
- `data/test_fixtures/model_30_minimal_payload.json`

Report interpretation:

- `verdict = "model_runtime"` means the local cold load or warm inference exceeded the configured thresholds, so slowness is likely inside artifact loading or model execution
- `verdict = "api_or_cache"` means both payloads stayed comfortably below the thresholds locally, so the deployed API path or cache layer is the more likely source
- `verdict = "inconclusive"` means the local measurements did not isolate a single bottleneck

The report also includes `timing_source`. On branches that already include the PR 195 adapter timing hooks, the harness uses those directly. On older branches it falls back to wall-clock timing around the same adapter call path.

## Latency comparison: Model 30 vs Model 21

> Generated pending manual benchmark run. Reproduce with:
> ```bash
> python -m scripts.diagnostics.compare_model_30_vs_21_latency \
>   --model both --mode both --warm-iterations 20 --cold-iterations 3 \
>   --mlflow-uri "$MLFLOW_SERVER_URL"
> ```

The benchmark is designed to show where model 30 diverges from the known-good model 21 route. The generated report highlights the first warm-path phase where model 30 exceeds either 2x the model 21 p50 or a +100 ms absolute delta, then pairs that with artifact size, cold-load, runtime metadata, and preprocessing complexity.

| Finding | Model 21 | Model 30 | Notes |
| --- | --- | --- | --- |
| Warm latency | Pending run | Pending run | Filled from `outputs/model_30_vs_21_latency_report.md` |
| Cold load | Pending run | Pending run | Uses fresh subprocess isolation per sample |
| Artifact size | Pending run | Pending run | Best-effort artifact inspection |
| Runtime/dependencies | Pending run | Pending run | Derived from artifact metadata |
| Preprocessing complexity | 10 derived features | 30 flattened features | Static comparison from serving code |
