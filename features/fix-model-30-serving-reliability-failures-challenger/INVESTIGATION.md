# HOK-1942: Model 30 Serving Reliability Failures — Investigation

## Evidence

From the 2026-05-31 24h CloudWatch service health report on
`/ecs/hokusai-api-development`:

- 35 Model 30 calls
- 4 Model 30 errors (~11.4% 503 rate)
- Sample error: `ERROR:src.api.endpoints.model_serving:Technical Task Router MLflow inference failed.`
- Sample HTTP: `POST /api/v1/models/30/predict` → `503 Service Unavailable`

This is user-facing through the Strategy Explorer; an 11% 503 rate over a small
window suggests a systematic failure mode rather than incidental noise.

## Per-Failure Attribution (4 errors, 2026-05-31 window)

REQ-F5 asks for each of the 4 CloudWatch failures to be attributed to a specific
phase with a quoted log excerpt. The pre-instrumentation log line did not carry
phase, exception class, or message as structured fields, so individual
attribution is **not possible from the existing logs**. The task packet
explicitly allows this fallback ("use CloudWatch event ID or timestamp as the
identifier and note the limitation"); the 4 failures are recorded below at the
fidelity the source data supports.

| # | CloudWatch identifier | Quoted log excerpt | Phase attribution | Confidence |
|---|---|---|---|---|
| 1 | `/ecs/hokusai-api-development` 2026-05-31 (timestamp unavailable in summary) | `ERROR:src.api.endpoints.model_serving:Technical Task Router MLflow inference failed.` | **Unattributable** — falls through the generic `except Exception` path | None |
| 2 | `/ecs/hokusai-api-development` 2026-05-31 (timestamp unavailable in summary) | `ERROR:src.api.endpoints.model_serving:Technical Task Router MLflow inference failed.` | **Unattributable** — same | None |
| 3 | `/ecs/hokusai-api-development` 2026-05-31 (timestamp unavailable in summary) | `ERROR:src.api.endpoints.model_serving:Technical Task Router MLflow inference failed.` | **Unattributable** — same | None |
| 4 | `/ecs/hokusai-api-development` 2026-05-31 (timestamp unavailable in summary) | `ERROR:src.api.endpoints.model_serving:Technical Task Router MLflow inference failed.` | **Unattributable** — same | None |

The CloudWatch service health report cited in the issue surfaces a count (4)
and a representative sample message, not the four individual log records.
Recovering per-event timestamps would require a CloudWatch Logs Insights query
against `/ecs/hokusai-api-development` over the 2026-05-31 24h window filtered
by `Technical Task Router MLflow inference failed`. The structured fields this
PR adds will make that attribution trivial for any future failure window.

## Pre-instrumentation Limitation

Before this PR, the only structured signal for a Model 30 inference failure was
the generic log line `Technical Task Router MLflow inference failed` emitted by
the `except Exception` block in `_serve_mlflow_prediction` plus the boilerplate
`extra={model_id, model_uri, request_id, run_id}` block. The actual exception
class, message, and the phase at which the failure occurred (artifact load,
predict call, response normalization, or MLflow connectivity issue) were not
captured in a structured form, only present in the Python traceback embedded in
the log message via `exc_info=exc`.

This made it impossible to:

1. Distinguish transient MLflow connectivity issues from deterministic artifact
   load or predict-call failures.
2. Quantify how many failures correlated with cold-path vs. warm-path requests.
3. Determine whether the population of failures shared a common exception class
   (e.g., `requests.exceptions.ConnectionError` vs. `MlflowException`).

In addition, all such failures were returned to the client as HTTP 503. 503 is
appropriate for transient conditions (the caller should retry); for
deterministic failures like a broken artifact or a non-recoverable predict-call
error, HTTP 500 is the more honest status.

## Hypothesis

Without structured fields, definitive classification of the 2026-05-31 failures
is not possible from existing logs. Likely candidates ordered by plausibility:

1. **Cold artifact load failure** — Model 30 has cold-start latency
   characteristics from MLflow `pyfunc.load_model`. A failed cold load (S3
   transient error, registry hiccup, or a partial deploy) would surface as a
   `RuntimeError` or `MlflowException` from the load path.
2. **MLflow registry connectivity** — `registry.hokus.ai` was reachable in the
   window, but transient network blips between API tasks and the registry are
   plausible.
3. **Predict-call failure** — the loaded artifact rejected the request payload.
   Less likely given that schema validation runs first and validated inputs are
   converted to a deterministic feature frame.

## What This PR Adds

After deployment, every Model 30 inference failure will emit a
`model_30_inference_failure` log record with these fields:

| Field | Meaning |
|---|---|
| `request_id` | Correlates to the contributor inference log id |
| `model_id` | Always `"30"` for this code path |
| `model_uri` | The MLflow model URI that was loaded/called |
| `model_version` | Configured registry version |
| `phase` | One of `artifact_load`, `predict_call`, `response_normalization`, `mlflow_connectivity`, `timeout` |
| `path_type` | `cold`, `warm`, or `unknown` from the latency trace |
| `exception_class` | Concrete underlying exception type |
| `exception_message` | Truncated to 500 chars to bound log size and avoid payload echo |

`phase` is set by classifying the exception at the failure site:

- `mlflow_connectivity` for `requests.exceptions.ConnectionError`,
  `requests.exceptions.Timeout`, or `MlflowException` whose message matches
  connection-related keywords (returns HTTP 503).
- `artifact_load` for any other exception from `_get_or_load_model_30`
  (returns HTTP 500).
- `predict_call` for exceptions raised by `model.predict(features)` or the
  generic fallback path (returns HTTP 500).
- `response_normalization` for exceptions in `normalize_model_30_output`
  (returns HTTP 500).
- `timeout` is unchanged; the existing `asyncio.TimeoutError` handler maps it
  to HTTP 504.

## Next Steps

After this PR is deployed:

1. Watch `/ecs/hokusai-api-development` for `model_30_inference_failure` events.
2. Aggregate by `phase` and `path_type`. The hypothesis is that the majority of
   failures will have `path_type=cold` and `phase∈{artifact_load,
   mlflow_connectivity}`.
3. Use `exception_class` to determine whether MLflow is returning structured
   errors or whether the failures originate further downstream (S3, registry
   HTTP layer, etc.).
4. If `mlflow_connectivity` dominates, follow up with a retry policy on the
   load path. If `artifact_load` dominates with non-connectivity exceptions,
   the registry artifact itself may need investigation.
