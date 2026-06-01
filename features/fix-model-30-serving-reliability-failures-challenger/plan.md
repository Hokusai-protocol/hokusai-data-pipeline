# Implementation Plan: Fix Model 30 Serving Reliability Failures (HOK-1942)

## Overview

Instrument the Model 30 (Technical Task Router) MLflow inference failure path with:
1. Phase classification (artifact_load, predict_call, response_normalization, timeout, mlflow_connectivity)
2. Structured error logging (request_id, model_uri/version, phase, path_type, exception_class/message)
3. Correct HTTP status per phase (503 for transient, 500 for deterministic)
4. Unit tests for each failure phase
5. Investigation document and docs update

No behavioral changes to the happy path. All changes are additive instrumentation plus corrected status codes on error paths.

---

## Phase 1: Add `Model30InferenceError` and phase classification to `model_30_adapter.py`

**File**: `src/api/endpoints/model_30_adapter.py`

### 1a. Add `Model30InferenceError` exception class

After `Model30LoadInProgressError`:

```python
class Model30InferenceError(RuntimeError):
    """Raised when Model 30 MLflow inference fails at a classified phase."""
    def __init__(self, message: str, *, phase: str) -> None:
        super().__init__(message)
        self.phase = phase
```

### 1b. Add `_classify_load_exception` helper

```python
def _classify_load_exception(exc: BaseException) -> str:
    """Return 'mlflow_connectivity' or 'artifact_load' for a load-phase exception."""
    import requests.exceptions  # local import to avoid top-level dep
    import mlflow.exceptions
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return "mlflow_connectivity"
    if isinstance(exc, mlflow.exceptions.MlflowException):
        msg = str(exc).lower()
        if any(kw in msg for kw in ("connection", "timeout", "network", "refused", "unreachable")):
            return "mlflow_connectivity"
    return "artifact_load"
```

### 1c. Update `call_mlflow_model_30` to wrap artifact load and predict call

```python
def call_mlflow_model_30(model_uri, features, _timings=None):
    load_started_at = time.perf_counter()
    try:
        model = _get_or_load_model_30(model_uri)
    except Model30LoadInProgressError:
        raise  # re-raise as-is; endpoint handles this separately
    except Exception as exc:
        if _timings is not None:
            _timings["artifact_load_ms"] = (time.perf_counter() - load_started_at) * 1000
        phase = _classify_load_exception(exc)
        raise Model30InferenceError(str(exc), phase=phase) from exc
    artifact_load_ms = (time.perf_counter() - load_started_at) * 1000

    predict_started_at = time.perf_counter()
    try:
        result = model.predict(features)
    except Exception as exc:
        if _timings is not None:
            _timings["artifact_load_ms"] = artifact_load_ms
            _timings["inference_only_ms"] = (time.perf_counter() - predict_started_at) * 1000
        raise Model30InferenceError(str(exc), phase="predict_call") from exc
    inference_only_ms = (time.perf_counter() - predict_started_at) * 1000

    if _timings is not None:
        _timings["artifact_load_ms"] = artifact_load_ms
        _timings["inference_only_ms"] = inference_only_ms
    return result
```

---

## Phase 2: Add `emit_model_30_inference_failure` to `validation_logging.py`

**File**: `src/api/middleware/validation_logging.py`

Add following `emit_model_serving_validation_422`:

```python
def emit_model_30_inference_failure(
    logger_: logging.Logger,
    *,
    request_id: str,
    model_id: str,
    model_uri: str,
    model_version: str,
    phase: str,
    path_type: str,
    exception_class: str,
    exception_message: str,
) -> None:
    """Emit a structured inference_failure record for Model 30 serving errors."""
    logger_.error(
        "model_30_inference_failure",
        extra={
            "event_type": "model_30_inference_failure",
            "request_id": request_id,
            "model_id": model_id,
            "model_uri": model_uri,
            "model_version": model_version,
            "phase": phase,
            "path_type": path_type,
            "exception_class": exception_class,
            "exception_message": exception_message[:500],
        },
    )
```

This follows the flat-key, no-nesting convention from HOK-1943.

---

## Phase 3: Update `_serve_mlflow_prediction` in `model_serving.py`

**File**: `src/api/endpoints/model_serving.py`

### 3a. Add imports

```python
from .model_30_adapter import Model30InferenceError, Model30LoadInProgressError
from ..middleware.validation_logging import emit_model_30_inference_failure
```

(The `Model30LoadInProgressError` import is already present; add `Model30InferenceError`.)

### 3b. Wrap response normalization

In `_serve_mlflow_prediction`, replace:
```python
with trace.phase("postprocessing_serialization"):
    predictions = output_normalizer(raw_model_output, validated_inputs)
```

With:
```python
with trace.phase("postprocessing_serialization"):
    try:
        predictions = output_normalizer(raw_model_output, validated_inputs)
    except Exception as exc:
        raise Model30InferenceError(str(exc), phase="response_normalization") from exc
```

### 3c. Add `except Model30InferenceError` handler

Insert between `except Model30LoadInProgressError` and `except ValidationError`:

```python
except Model30InferenceError as exc:
    trace.outcome = exc.phase
    if not trace_emitted:
        trace.emit(logger)
        trace_emitted = True
    cause = exc.__cause__ or exc
    emit_model_30_inference_failure(
        logger,
        request_id=request_id,
        model_id=model_id,
        model_uri=model_uri,
        model_version=entry.model_version or "unknown",
        phase=exc.phase,
        path_type=trace.path_type,
        exception_class=type(cause).__name__,
        exception_message=str(cause),
    )
    status_code = 503 if exc.phase == "mlflow_connectivity" else 500
    raise HTTPException(
        status_code=status_code,
        detail={
            "error": f"{entry.name} inference failed ({exc.phase}): {cause}",
            "request_id": request_id,
            "run_id": trace.run_id,
            "phase": exc.phase,
        },
    ) from exc
```

### 3d. Update the generic `except Exception as exc:` fallback

The fallback now handles truly unexpected errors (not classified by `call_mlflow_model_30`). Update to:
- Call `emit_model_30_inference_failure` with fallback phase `"predict_call"` (per spec)
- Return HTTP 500 (not 503 — these are unexpected/deterministic failures, not transient)
- Return structured dict detail (same shape as above)
- Remove the old `logger.error` call (replaced by `emit_model_30_inference_failure`)

```python
except Exception as exc:
    trace.outcome = "error"
    if not trace_emitted:
        trace.emit(logger)
    emit_model_30_inference_failure(
        logger,
        request_id=request_id,
        model_id=model_id,
        model_uri=model_uri,
        model_version=entry.model_version or "unknown",
        phase="predict_call",
        path_type=trace.path_type,
        exception_class=type(exc).__name__,
        exception_message=str(exc),
    )
    raise HTTPException(
        status_code=500,
        detail={
            "error": f"{entry.name} MLflow inference failed: {exc}",
            "request_id": request_id,
            "run_id": trace.run_id,
            "phase": "predict_call",
        },
    ) from exc
```

**Note**: The existing `test_model_30_predict_mlflow_failure_returns_503` test (which raises a raw `RuntimeError`) must be updated to expect HTTP 500 and a dict detail, as `RuntimeError` is not a connectivity exception and falls into the deterministic failure path.

---

## Phase 4: Add tests to `test_model_30_adapter.py`

**File**: `tests/unit/test_model_30_adapter.py`

Add the following tests:

1. `test_call_mlflow_model_30_load_exception_wraps_as_inference_error` — mock `mlflow.pyfunc.load_model` to raise RuntimeError, assert `Model30InferenceError` is raised with `phase="artifact_load"`
2. `test_call_mlflow_model_30_connectivity_exception_classified_as_mlflow_connectivity` — mock `mlflow.pyfunc.load_model` to raise `requests.exceptions.ConnectionError`, assert `phase="mlflow_connectivity"`
3. `test_call_mlflow_model_30_predict_exception_wraps_as_inference_error` — mock `model.predict` to raise RuntimeError, assert `Model30InferenceError(phase="predict_call")`
4. `test_classify_load_exception_connection_error` — unit test `_classify_load_exception` with ConnectionError
5. `test_classify_load_exception_mlflow_exception_connectivity_msg` — unit test with MlflowException containing "connection refused"
6. `test_classify_load_exception_generic_error` — unit test with RuntimeError → "artifact_load"
7. `test_call_mlflow_model_30_populates_timings_on_load_error` — assert `artifact_load_ms` in timings even when load fails

---

## Phase 5: Update tests in `test_model_serving.py`

**File**: `tests/unit/test_model_serving.py`

### 5a. Update existing test

`test_model_30_predict_mlflow_failure_returns_503` → rename to `test_model_30_predict_unclassified_failure_returns_500_with_phase`, update assertions:
- `status_code == 500` (was 503)
- `detail["error"].startswith("Technical Task Router MLflow inference failed")`
- `detail["request_id"]` is non-empty
- `detail["phase"] == "predict_call"`

### 5b. Add new tests

1. `test_model_30_predict_mlflow_connectivity_failure_returns_503` — `model_caller` raises `requests.exceptions.ConnectionError` wrapped as `Model30InferenceError(phase="mlflow_connectivity")` → expect 503, `detail["phase"] == "mlflow_connectivity"`
2. `test_model_30_predict_artifact_load_failure_returns_500_with_phase` — `model_caller` raises `Model30InferenceError(phase="artifact_load")` → expect 500, `detail["phase"] == "artifact_load"`
3. `test_model_30_predict_response_normalization_failure_returns_500_with_phase` — `output_normalizer` raises ValueError, expect 500, `detail["phase"] == "response_normalization"`
4. `test_model_30_failure_log_contains_structured_fields` — assert `caplog` record has keys: `event_type`, `request_id`, `model_id`, `model_uri`, `model_version`, `phase`, `path_type`, `exception_class`, `exception_message`
5. `test_model_30_failure_log_truncates_long_exception_message` — assert exception message > 500 chars is truncated to 500

---

## Phase 6: Create `INVESTIGATION.md`

**File**: `features/fix-model-30-serving-reliability-failures-challenger/INVESTIGATION.md`

Document:
- Evidence from the 2026-05-31 CloudWatch report (4 errors / 35 calls = 11.4% 503 rate)
- Pre-instrumentation limitation: no `phase`, `path_type`, or `exception_class` fields were present
- Available information: generic `Technical Task Router MLflow inference failed` log line + 503 HTTP response
- Likely classification: The log message comes from the `except Exception` block in `_serve_mlflow_prediction`, which previously caught all non-timeout, non-validation errors. Without structured context, definitive classification is not possible.
- Hypothesis: cold-load artifact failures are the most likely cause given the cold-start latency characteristics of MLflow pyfunc models, but this cannot be confirmed until the new instrumentation is deployed
- Next steps: deploy this PR, observe `/ecs/hokusai-api-development` for `model_30_inference_failure` events with `phase`, `path_type`, and `exception_class` fields

---

## Phase 7: Update `docs/model-30-serving.md`

Add a "Failure Phases" section documenting:
- Five phase values and what each means
- Log field schema (table)
- Phase → HTTP status mapping
- Example log snippet

---

## Release Readiness

- `database_change_risk`: none
- `env_changes`: none
- `config_changes`: none
- `manual_steps`: none

---

## Key Decisions

1. **`Model30InferenceError` in adapter vs endpoint**: Wrapping in the adapter (at the MLflow call boundary) is correct per the task spec and keeps classification close to the originating exception. The normalization wrapper in the endpoint completes the full phase coverage.

2. **HTTP status change for generic fallback**: The old generic handler returned 503 for all exceptions. Per REQ-F4, `predict_call` should be 500. Updating this requires updating `test_model_30_predict_mlflow_failure_returns_503` (rename + status change).

3. **No new module**: `emit_model_30_inference_failure` goes in `validation_logging.py` (same module as `emit_model_serving_validation_422`), co-locating all Model 30 structured logging helpers.

4. **Exception message truncation**: 500 chars to bound log size and prevent payload echo via exception strings (per spec constraint).

5. **`trace.outcome` for `Model30InferenceError`**: Set to `exc.phase` (one of the five values), which enriches the existing latency trace log for failed requests.
