# HOK-1942 Investigation — Model 30 Serving Reliability

## Evidence Window

Source: 2026-05-31 24-hour CloudWatch service health report against `/ecs/hokusai-api-development`.

- Total `POST /api/v1/models/30/predict` calls in the window: **35**
- Total errors logged with `Technical Task Router MLflow inference failed`: **4**
- Observed 503 rate: **~11%**
- All error samples produced HTTP `503 Service Unavailable`; no `504` samples surfaced for Model 30 in the same window.

## CloudWatch Query Template

The pre-change `_serve_mlflow_prediction()` collapsed every MLflow-side failure into one log line — `Technical Task Router MLflow inference failed` — with no `phase`, `path_type`, `model_version`, or `exception_class` fields. The only structured signal available for classification was the parent `model_30_latency_trace` record with `outcome=error`.

Queries used / would use against CloudWatch Logs Insights:

```sql
-- Raw error samples (pre-change view)
fields @timestamp, @message
| filter @message like /Technical Task Router MLflow inference failed/
| sort @timestamp desc
| limit 200
```

```sql
-- Correlate failures to latency traces (pre-change view)
fields @timestamp, request_id, path_type, outcome, dominant_phase,
       artifact_load_ms, model_inference_ms, total_ms
| filter event = "model_30_latency_trace" and outcome = "error"
| sort @timestamp desc
| limit 50
```

```sql
-- After this change: classify by structured phase
fields @timestamp, request_id, phase, path_type, exception_class,
       exception_message, duration_ms
| filter event_type = "model_30_inference_failure"
| stats count() as failures by phase
| sort failures desc
```

Direct AWS access from the worktree is not available, so the per-phase counts cannot be produced until the structured logger is deployed and the query above is re-run against the next 24-hour window.

## Pre-Change Classification of Available Samples

The only sample shipped in the task description is:

```
ERROR:src.api.endpoints.model_serving:Technical Task Router MLflow inference failed.
```

That log line is emitted from the catch-all `except Exception` branch in `_serve_mlflow_prediction()`. It can come from any of four code paths:

1. `_get_or_load_model_30(model_uri)` raising during cold load (registry/artifact problem)
2. `_get_or_load_model_30(model_uri)` raising due to network failure (MLflow connectivity)
3. `model.predict(features)` raising on the loaded artifact (predict-time error)
4. `normalize_model_30_output(...)` raising on unexpected MLflow output shape (normalization error)

A separate `asyncio.TimeoutError` branch covers timeouts and returns `504`. No `504` samples surfaced in the window, so timeout is not the dominant class for these four samples.

Without structured fields the four samples cannot be partitioned across paths 1–4 from log content alone. Each sample is consistent with any of the four phases.

| Phase                     | Distinguishable from pre-change log? | Count from sample window |
|---------------------------|--------------------------------------|--------------------------|
| `artifact_load`           | No                                   | unknown                  |
| `mlflow_connectivity`     | No                                   | unknown                  |
| `predict_call`            | No                                   | unknown                  |
| `response_normalization`  | No                                   | unknown                  |
| `timeout`                 | Yes (separate handler → 504)         | 0 in sampled window      |

## Dominant Failure Class

**Indeterminate from the pre-change logs.** The investigation confirmed that the dominant cause cannot be named with the data currently in CloudWatch. The acceptance-criteria question "do failures correlate with cold artifact loads or MLflow service errors?" cannot be answered without `phase` and `path_type` fields on the error record.

## Chosen Remediation

Add the observability needed to make the dominant class determinable on the next 24-hour window, instead of guessing at remediation now.

The remediation lands in three pieces, all in this branch:

1. **Five-phase taxonomy in `src/api/endpoints/model_30_adapter.py`**
   - `Model30FailurePhase` enum with `ARTIFACT_LOAD`, `PREDICT_CALL`, `RESPONSE_NORMALIZATION`, `TIMEOUT`, `MLFLOW_CONNECTIVITY`.
   - `Model30InferenceError` carries the originating phase and original exception.
   - `_is_connectivity_error()` classifies loader exceptions that look like network errors vs. artifact errors.
   - `call_mlflow_model_30()` and `normalize_model_30_output()` wrap their failure paths so the phase is attached at the point that knows it.

2. **Structured failure logger in `src/api/endpoints/model_serving.py`**
   - `log_model_30_failure()` emits one `model_30_inference_failure` record per failure with `request_id`, `model_uri`, `model_version`, `phase`, `path_type`, `exception_class`, `exception_message`, and `duration_ms`.
   - The three existing exception handlers (timeout / cold-load contention / catch-all) all call this helper. The 503/504 response shapes are unchanged so Strategy Explorer parsing is unaffected.

3. **No retry, gating, or behavior change** — adding fallbacks or retries without first knowing the dominant class would risk masking the failure. The deliverable is the data needed to choose the right next step.

After deploy, run the per-phase Logs Insights query above against the next 24-hour window. The phase with the highest count becomes the target for the follow-up fix (e.g. an `artifact_load`-dominant result points at registry hygiene or warm-up; a `mlflow_connectivity`-dominant result points at network/TLS/health-check work; a `predict_call`-dominant result points at feature drift or model regression).

## Tests Added

- `tests/unit/test_model_30_adapter.py` — five tests, one per failure phase: assert `Model30InferenceError.phase` matches the path that raised, including the cold-vs-warm path-type discrimination test.
- `tests/unit/test_model_serving.py` — endpoint-level assertions that the structured record is emitted exactly once per failure with the contracted fields, including the timeout (504) path, the catch-all 503 path, and the response-normalization 503 path.

## Open Follow-Ups (Out of Scope for This PR)

- Re-run the Logs Insights phase-count query on the next 24-hour window after deploy and update this document with the actual counts and the named dominant phase.
- Once the dominant phase is known, file a follow-up to implement the targeted remediation (retry, warm-up, registry hygiene, or feature/model regression fix — depending on what wins).
