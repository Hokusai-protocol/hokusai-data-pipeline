# Model 30 Serving

`POST /api/v1/models/30/predict` serves the registered MLflow Technical Task Router model through the public nested request contract `technical_task_router_inputs/v2`.

`POST /api/v1/models/30/contributions` accepts contribution batches from Wavemill and `hokusai-site` for persistence and downstream processing.

## Contribution Endpoint

Authentication is required. Clients may submit either:

- Wavemill batch shape: `{"rows":[...],"metadata":{"idempotency_key":"..."}}`
- Site shape: `{"modelId":"30","benchmarkSpecId":null,"rows":[...],"schemaVersion":null,"templateId":null}`

Behavior:

- Path: `/api/v1/models/{model_id}/contributions`
- Method: `POST`
- `Idempotency-Key` header takes precedence over `metadata.idempotency_key`
- `rows` is required, must contain 1 to 10000 JSON objects
- `modelId` in the body must match the path when present
- First acceptance returns `201`; identical idempotent replay returns `200`
- Reusing an idempotency key with a different payload returns `409`
- Missing persistence configuration returns `503`

Response fields include `accepted`, `modelId`, `submissionId`, `jobId`, `jobIds`, `rowsAccepted`, `submittedRows`, and `tokenReward`.

Persistence is S3-backed and controlled by `HOKUSAI_CONTRIBUTIONS_BUCKET`, optional `HOKUSAI_CONTRIBUTIONS_PREFIX`, and `CONTRIBUTIONS_MAX_BODY_BYTES`.

## Public Contract

Accepted `inputs` groups:

- `task` (required)
- `routing`
- `context`
- `workflow`
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

Historical outcome and training-label groups such as `prediction`, `outcome`, and `rubric` are also rejected. Live callers configure the task and routing constraints only; they do not supply observed cost, success, score, or selected model labels.

The v2 routing contract supports three user-facing objectives:

- `lowest_cost`
- `fastest_completion`
- `highest_reliability`

Workflow stages are selected with `workflow.stages` and may include `plan`, `code`, and `review`. The caller can restrict the model set globally with `routing.available_models` or per role with `routing.available_planner_models`, `routing.available_coder_models`, and `routing.available_reviewer_models`.

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
      "available_models": ["claude-sonnet-4-6", "gpt-5.4"],
      "max_cost_usd": 25,
      "objective": "highest_reliability"
    },
    "workflow": {
      "stages": ["plan", "code", "review"]
    },
    "context": {
      "domain": "payments",
      "repo_size_bucket": "large",
      "requires_tests": true,
      "risk_level": "medium",
      "file_count": 6,
      "estimated_complexity": "medium",
      "security_sensitive": true
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
    "allowed_models": ["gpt-5.4"],
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

Training data validation and provenance requirements are documented in [Model 30 Training Data](model-30-training-data.md).

Environment variables:

- `MODEL_30_MLFLOW_URI` defaults to `models:/Technical Task Router@production`
- `MLFLOW_TRACKING_URI` must point at the registry/tracking server
- Any auth token or mTLS environment expected by the deployed MLflow stack must also be present

The API startup path already configures MLflow mTLS behavior in `src/api/main.py` through `src/utils/mlflow_config.configure_internal_mtls()`. This serving path relies on that shared setup and does not duplicate transport configuration.

## Adapter Behavior

The current serving path validates the nested request, maps it into a one-row pandas feature frame, calls `mlflow.pyfunc.load_model(model_uri).predict(...)`, then normalizes raw output into the v2 strategy-router response:

```json
{
  "recommended_strategy": {
    "objective": "highest_reliability",
    "planner_model": "claude-sonnet-4-6",
    "coder_model": "gpt-5.4",
    "reviewer_model": "claude-sonnet-4-6",
    "stages": ["plan", "code", "review"],
    "estimated_success_under_budget": 0.82,
    "estimated_cost_usd": 4.8,
    "estimated_duration_seconds": 1800,
    "confidence": 0.71
  },
  "alternatives": [],
  "tradeoffs": {
    "lowest_cost": null,
    "fastest_completion": null,
    "highest_reliability": null
  },
  "nearest_neighbors": {
    "count": 40,
    "success_under_budget_rate": 0.78,
    "mean_cost_usd": 4.4,
    "mean_duration_seconds": 1650
  }
}
```

The normalizer validates strategy outputs against the public response schema and rejects malformed model identifiers such as `deep-coder-v2`, `fast-coder-v1`, and `<synthetic>`. It keeps a compatibility shim for older smoke artifacts that emit only legacy selected-model fields, but the production Technical Task Router artifact is expected to emit the v2 strategy payload directly.

For legacy smoke artifacts only, normalization accepts common aliases:

- `model`, `selected`, `prediction` -> legacy selected model
- `models` -> legacy selected models
- `score`, `probability` -> confidence
- `cost`, `estimated_cost` -> estimated cost

There is no deterministic fallback when MLflow is configured. Load, predict, or normalization failures return `503` with a `Model 30 MLflow inference failed` prefix.

## Usage Debit Rejection

When the auth service rejects a usage debit, the API returns `402 Payment Required` before the model runs:

```json
{
  "error": "usage_debit_rejected",
  "reason": "Settled balance 0.00 insufficient. Pending: 0.00 (not yet spendable).",
  "reason_code": "insufficient_settled_balance"
}
```

The downstream handler is not invoked. Clients should top up their balance and retry.

## Startup Lifecycle

At process startup the API now performs two separate MLflow steps:

- `_prewarm_mlflow_registered_models()` verifies registry connectivity for all MLflow-backed models.
- `warm_model_30()` then loads the model 30 artifact into the in-process cache and runs a minimal valid prediction using `data/test_fixtures/model_30_minimal_payload.json`.

The model 30 warm runs in a background task after MLflow mTLS and tracking URI setup complete. The process can come up quickly, but `/ready` does not report traffic-ready until the warm path finishes successfully.

Set `MODEL_30_PREWARM_ENABLED=false` to disable startup warm during rollback. In that mode, `/ready` no longer blocks on `not_started` and model 30 falls back to the existing on-demand cold-load path.

Operational note from HOK-1876:

- The ECS API task currently runs with `cpu = "512"` and `memory = "1024"` and does not set `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, or `OPENBLAS_NUM_THREADS`.
- The recommended first operational experiment is to pin those thread env vars to `1` before attempting heavier Model 30 runtime changes.

## Readiness Contract

`GET /ready` now exposes model 30 warm state separately from lightweight liveness:

- `warming` or `not_started` while prewarm is enabled: HTTP `503`, `can_serve_traffic=false`
- `warmed`: HTTP `200`, `ready=true`, `model_30.warmed=true`
- `failed`: HTTP `200`, degraded mode, with `model_30.state="failed"` and `last_error`

Response payloads include:

- `model_30.warmed`
- `model_30.state`
- `model_30.warmed_at`
- `model_30.last_error`
- `model_30.duration_ms`
- `warmup_duration_ms`

This lets ALB or clients distinguish "process alive" from "inference ready".

## Latency & Reliability Budget

`configs/model_30_budget.yaml` is the canonical source for the thresholds below. The table reflects the same values and is what `scripts/model_30/latency_smoke_check.py` enforces in CI.

| Metric | Soft threshold | Hard threshold | Baseline (observed) | How measured |
|--------|----------------|----------------|---------------------|--------------|
| `cold_readiness_ms` | 30000 ms | 60000 ms | Pending CI capture | Wall-clock time from smoke-check start until `/ready` reports `ready=true` and `model_30.warmed=true` |
| `artifact_load_ms` | 15000 ms | 25000 ms | Pending CI capture | `GET /ready` `warmup_duration_ms`, which aliases `model_30.duration_ms` and reflects startup artifact load plus warm prediction |
| `warm_p50_ms` | 300 ms | 600 ms | Pending CI capture | Client-observed p50 for sequential curated `POST /api/v1/models/30/predict` requests |
| `warm_p95_ms` | 800 ms | 1500 ms | Pending CI capture | Client-observed p95 for the same warm request sample |
| `warm_p99_ms` | 1500 ms | 3000 ms | Pending CI capture | Client-observed p99 for the same warm request sample |
| `timeout_rate` | 0.00 | 0.02 | Pending CI capture | `model_30_timeout` responses divided by `success + model_30_timeout` samples |
| `warm_memory_mb` | 800 MB | 1200 MB | Pending CI capture | API container RSS after the warm request run |
| `cold_memory_mb` | 1200 MB | 1800 MB | Pending CI capture | API container RSS immediately after container startup, before the latency sample finishes |

Soft threshold breaches annotate CI but do not fail the job. Hard threshold breaches fail the budget check and block the PR.

Exit codes used by the smoke check:

| Exit code | Meaning |
|-----------|---------|
| `0` | Pass, or soft-only breaches |
| `10` | Model 30 latency or timeout hard breach |
| `11` | Model 30 route-specific error excess |
| `20` | Infra inconclusive (for example auth, shared route, or network failures dominate the sample) |

### Responding to a budget regression

Fetch the `model-30-smoke-report` workflow artifact and inspect `model_30_smoke_report.json`. The report includes raw metrics, soft and hard breach lists, infra classification counts, and per-request sample classifications.

If the report shows a real regression, fix the underlying warm path, artifact load, or inference latency issue and rerun the workflow. If the threshold is wrong after reviewing the baseline, update `configs/model_30_budget.yaml` in the same change so the source of truth and the gate stay aligned.

When the report classifies the run as `infra_inconclusive`, treat it as a shared route, auth, or network issue first. Those failures are intentionally separated from Model 30-specific regressions so the latency budget does not mask a broken environment.

The startup warm timeout is controlled by `MODEL_30_WARM_TIMEOUT_S`.

## Failure Classes and Observability

Every inference path that surfaces a non-2xx response also emits exactly one structured `model_30_inference_failure` log record so failures can be classified without reading stack traces. The taxonomy isolates which stage failed so on-call can distinguish artifact-load problems from connectivity blips from model output regressions.

### Failure phases

| `phase`                  | Where it fires                                                          | Typical cause                                                                 | HTTP status |
|--------------------------|-------------------------------------------------------------------------|-------------------------------------------------------------------------------|-------------|
| `artifact_load`          | `mlflow.pyfunc.load_model(...)` raised, or another loader holds the lock | Registry returned no artifact, deserialization failed, or cold-load contention | 503         |
| `mlflow_connectivity`    | Loader raised an `OSError`/`ConnectionError` or matched connectivity keywords | Tracking server unreachable, TLS reset, 503 from MLflow, DNS failure          | 503         |
| `predict_call`           | `model.predict(features)` raised                                          | Feature/schema mismatch, model code bug, model-internal exception              | 503         |
| `response_normalization` | `normalize_model_30_output(...)` raised after a successful predict       | Empty MLflow output, unsupported output shape, missing `selected_model`        | 503         |
| `timeout`                | `asyncio.wait_for(...)` exceeded `MODEL_SERVING_PREDICTION_TIMEOUT_SECONDS` | Slow cold load, slow inference, registry slowdown                              | 504         |

The 503 response body shape is unchanged: `{"detail": "Technical Task Router MLflow inference failed: <exc>"}`. The 504 body keeps its `{error, request_id, run_id}` shape. Strategy Explorer parsing is unaffected.

### `model_30_inference_failure` log fields

Every record carries the same field contract so a single CloudWatch query can pivot across all phases:

| Field               | Type            | Notes                                                                                      |
|---------------------|-----------------|--------------------------------------------------------------------------------------------|
| `event_type`        | string (constant) | Always `"model_30_inference_failure"`                                                      |
| `request_id`        | string          | Same id returned in the API response `metadata.request_id` and persisted with inference logs |
| `model_uri`         | string          | E.g. `models:/Technical Task Router/4`                                                     |
| `model_version`     | string \| null  | `MODEL_30_VERSION` when available; `null` if the registry entry has none                   |
| `phase`             | string enum     | One of the values in the phase table above                                                 |
| `path_type`         | string          | `cold`, `warm`, or `unknown` if the failure preceded `set_path_type`                       |
| `exception_class`   | string          | `type(exc).__name__` (e.g. `RuntimeError`, `TimeoutError`, `ConnectionError`)              |
| `exception_message` | string          | `str(exc)` truncated to 500 chars                                                          |
| `duration_ms`       | number          | Wall-clock from request entry to the failure, rounded to 2 decimals                        |

Example log line (JSON formatter output):

```json
{
  "level": "ERROR",
  "msg": "model_30_inference_failure",
  "event_type": "model_30_inference_failure",
  "request_id": "8b1f4d7e-6c5a-4b8b-9a2e-7c0e7a8d9e10",
  "model_uri": "models:/Technical Task Router/4",
  "model_version": "4",
  "phase": "mlflow_connectivity",
  "path_type": "cold",
  "exception_class": "ConnectionError",
  "exception_message": "HTTPConnectionPool(host='mlflow.hokusai-development.local', port=5000): Max retries exceeded",
  "duration_ms": 412.37
}
```

### CloudWatch Logs Insights queries

Count failures by phase over the recent window:

```sql
fields @timestamp, request_id, phase, path_type, exception_class, duration_ms
| filter event_type = "model_30_inference_failure"
| stats count() as failures by phase
| sort failures desc
```

Pull recent failure samples grouped by phase:

```sql
fields @timestamp, request_id, phase, path_type, exception_class, exception_message, duration_ms
| filter event_type = "model_30_inference_failure"
| sort @timestamp desc
| limit 50
```

Correlate a 503 sample to its structured record by `request_id` returned in the API response, or join to the matching `model_30_latency_trace` record (same `request_id`) to see which phase dominated wall-clock.

## Nested API To Router Feature Mapping

Model 30 is served from the nested public API contract, but its live prediction frame uses the Wavemill router feature schema it was trained on. `model_30_inputs_to_features()` delegates to `map_nested_to_router_features()` and emits only router input columns:

- Direct task/context/workflow fields: `task_type`, `language`, `framework`, `repo_type`, `domain`, `risk_level`, `requires_tests`, `security_sensitive`, `repo_size_bucket`, and `surface`
- Derived buckets: `description_length_bucket` from task description length and `files_touched_bucket` from `context.file_count`
- `complexity` from `context.estimated_complexity` when present, otherwise a description/file-count fallback
- Role availability arrays: `available_planner_models`, `available_coder_models`, and `available_reviewer_models` use the role-specific routing lists when provided and otherwise fall back to the sorted, deduped `routing.available_models` list
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

## Production Promotion

Use the HOK-1917 promotion script to register the cleaned Wavemill router model, log holdout metrics, set the MLflow `production` alias, and optionally smoke test the public API across all three routing objectives:

```bash
python scripts/model_30/promote_technical_task_router.py \
  --router-dataset data/model_30/hokusai-router-dataset.clean.csv \
  --holdout-dataset data/model_30/hokusai-router-holdout.clean.csv \
  --tracking-uri "$MLFLOW_TRACKING_URI" \
  --alias production \
  --production-smoke \
  --api-key "$HOKUSAI_API_KEY" \
  --output-report outputs/model-30-production-promotion.json
```

To promote an already registered version without retraining:

```bash
python scripts/model_30/promote_technical_task_router.py \
  --model-uri 'models:/Technical Task Router/5' \
  --alias production \
  --production-smoke \
  --api-key "$HOKUSAI_API_KEY"
```

The report captures the previous alias target and prints a rollback command when one exists. Rollback is alias-based, for example:

```bash
python scripts/model_30/promote_technical_task_router.py \
  --model-uri 'models:/Technical Task Router/4' \
  --alias production \
  --no-production-smoke
```

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
