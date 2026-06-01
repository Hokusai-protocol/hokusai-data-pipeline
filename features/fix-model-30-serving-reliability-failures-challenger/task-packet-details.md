## 1. Objective

### What
Diagnose, classify, and instrument the MLflow inference failure paths for Model 30 (`POST /api/v1/models/30/predict`) so that the ~11% 503 rate observed on 2026-05-31 can be attributed to a specific failure phase, then add regression tests once root cause is identified.

### Why
Model 30 (Technical Task Router) is user-facing through the Strategy Explorer path. CloudWatch `/ecs/hokusai-api-development` shows 4 errors out of 35 calls in a 24h window, with the generic log line `Technical Task Router MLflow inference failed` and 503 responses. Without phase classification and structured context, on-call cannot tell whether the failures are caused by cold artifact loads, predict-time errors, response normalization, timeouts, or MLflow service errors. The follow-up task HOK-1943 already established the structured-logging pattern for 422 validation failures; this task extends the same discipline to the 503 path.

### Scope In
- Audit existing failure-handling code paths in `src/api/endpoints/model_serving.py` and `src/api/endpoints/model_30_adapter.py`.
- Introduce a phase classifier that tags each failure with one of: `artifact_load`, `predict_call`, `response_normalization`, `timeout`, `mlflow_connectivity`.
- Add structured log fields: `request_id`, `model_id`, `model_uri`, `model_version`, `phase`, `path_type` (`cold`|`warm`), `exception_class`, `exception_message`.
- Distinguish cold (first-load) from warm (cached-model) invocations using whatever cache/state already exists in the adapter.
- Pull CloudWatch samples (within the documented window) and attribute them to phases; record findings in `features/fix-model-30-serving-reliability-failures-challenger/INVESTIGATION.md`.
- Add or update unit tests for the failing path(s) once classified.
- If a clear root cause is identified (e.g., MLflow client timeout too low, missing retry on cold artifact pull), implement a minimal fix.

### Scope Out
- No changes to MLflow server configuration or infrastructure (handled in `hokusai-infrastructure`).
- No new model versions or registry mutations.
- No changes to the Strategy Explorer / site UI.
- No changes to auth or billing middleware.
- No broad refactor of `model_serving.py` beyond what is needed for the classifier and logging.
- No changes to other model IDs' serving paths unless the classifier is naturally generic — Model 30 only.

---

## 2. Technical Context

### Repository
`hokusai-data-pipeline` (this repository). No changes expected to `hokusai-infrastructure`, `hokusai-auth-service`, `hokusai-site`, or `hokusai-docs`.

### Key Files
- `src/api/endpoints/model_serving.py` — current site of the `Technical Task Router MLflow inference failed` error log; the predict endpoint dispatches to the Model 30 adapter here.
- `src/api/endpoints/model_30_adapter.py` — wraps MLflow load + predict for Model 30 (Technical Task Router); primary place to instrument phases.
- `src/api/endpoints/latency_trace.py` — existing structured trace helper used for Model 30 latency comparison; extend rather than duplicate.
- `src/api/middleware/validation_logging.py` — recently added (commit `7be4cc8`, HOK-1943) for 422 structured logging; mirror the style and field naming.
- `src/api/main.py` — request_id propagation / middleware registration; verify the request_id is reachable at the error site.
- `tests/unit/test_model_serving.py` — unit tests for the predict endpoint.
- `tests/unit/test_model_30_adapter.py` — unit tests for the Model 30 adapter.
- `tests/integration/test_model_30_mlflow_serving.py` — integration smoke test.
- `tests/diagnostics/test_reproduce_model_30_inference.py` — diagnostics harness; useful for reproducing cold-path failures locally.
- `features/fix-model-30-serving-reliability-failures-challenger/INVESTIGATION.md` (new) — evidence write-up mirroring HOK-1943's `INVESTIGATION.md`.
- `docs/model-30-serving.md` — public-facing notes; update with the new failure phase taxonomy.

### Relevant Subsystem Specs

> ⚠️ **Knowledge Gap**: No `.wavemill/context/` subsystem specs were provided in the codebase context for the model-serving subsystem. After implementation, consider running `wavemill context init --force` to create subsystem documentation for `src/api/endpoints/model_serving.py` and `src/api/endpoints/model_30_adapter.py` so future Model 30 reliability work benefits from persistent context.

### Dependencies
- HOK-1943 (commit `7be4cc8`) established the structured logging pattern for Model 30 (validation 422s). This task layers on top of that pattern for the 503 path.
- MLflow client library (loaded via `src/utils/mlflow_config.py` / `src/utils/mlflow_dynamic_config.py`).
- CloudWatch log group `/ecs/hokusai-api-development` (read-only, for evidence-gathering only).

### Architecture Notes
- The 503 error path comes through `model_serving.py`'s exception handler that logs `Technical Task Router MLflow inference failed`. The adapter (`model_30_adapter.py`) is what actually calls MLflow; the endpoint catches the exception.
- Classification must happen as close to the originating exception as possible — wrap each MLflow interaction (`mlflow.pyfunc.load_model`, the actual `.predict()` call, and response normalization) in its own try/except that re-raises with a `phase` attribute or wraps in a typed internal exception.
- `path_type=cold` should reflect whether the model artifact had to be loaded for this request vs reused from an in-process cache. Check `model_30_adapter.py` for the existing caching strategy before introducing new state.
- Use the same log key convention as `validation_logging.py` (see commit `7be4cc8`) — flat keys like `request_id`, `model_id=30`, `phase`, `path_type`, etc.
- 503 must be returned ONLY for `mlflow_connectivity` and `timeout` phases (transient). `predict_call` and `response_normalization` errors are typically deterministic and should return 500. Confirm the current code's status mapping before changing it.

---

## 3. Implementation Approach

1. **Read the current failure path.** Open `src/api/endpoints/model_serving.py` and `src/api/endpoints/model_30_adapter.py` end-to-end. Identify (a) where `Technical Task Router MLflow inference failed` is logged, (b) every place MLflow is invoked, (c) where the 503 vs 500 decision is made, and (d) whether request_id is in scope at the error site.

2. **Gather evidence from CloudWatch.** Use `aws logs tail /ecs/hokusai-api-development` (or `aws logs filter-log-events`) for the 2026-05-31 window to capture the 4 error stack traces. Map each to one of the five phases by exception type / message. Record sample log lines (with timestamps and request IDs) in `features/fix-model-30-serving-reliability-failures-challenger/INVESTIGATION.md`.

3. **Define the phase taxonomy.** Add a `FailurePhase` enum (or string literals) with values `artifact_load`, `predict_call`, `response_normalization`, `timeout`, `mlflow_connectivity` in a small helper module — either extend `latency_trace.py` or add `src/api/endpoints/model_30_failure_phases.py` (new). Prefer extending the existing trace module to keep all Model 30 instrumentation co-located.

4. **Wrap each MLflow interaction in `model_30_adapter.py`** with a try/except that catches the narrowest expected exception types (`mlflow.exceptions.MlflowException`, `requests.exceptions.ConnectionError`, `requests.exceptions.Timeout`, `KeyError`/`ValueError` for normalization) and re-raises a typed wrapper carrying the `phase` and the original cause.

5. **Track cold vs warm path** by checking the cached-model state immediately before load. If no cache exists, introduce a minimal one (single-process dict keyed by `model_uri`) ONLY if the adapter doesn't already cache. If a cache already exists, just read its state.

6. **Update the endpoint error handler in `model_serving.py`** to unpack the typed wrapper exception and emit a single structured log line containing: `request_id`, `model_id=30`, `model_uri`, `model_version`, `phase`, `path_type`, `exception_class`, `exception_message`. Use the existing logger; do not add a new logging framework.

7. **Map phase → HTTP status.** Return 503 only for `mlflow_connectivity` and `timeout`; return 500 for `artifact_load` (unless caused by connectivity, in which case it's already classified that way), `predict_call`, and `response_normalization`. Verify this matches current behavior before changing.

8. **Write unit tests** in `tests/unit/test_model_30_adapter.py` and `tests/unit/test_model_serving.py`:
   - Mock each MLflow call to raise a specific exception → assert the classified `phase` in the log payload and the HTTP status code.
   - Cold-path test (no cached model) → assert `path_type=cold`.
   - Warm-path test (model already in cache) → assert `path_type=warm`.

9. **Run the diagnostics reproduction script** (`scripts/diagnostics/reproduce_model_30_inference.py`) against dev to confirm warm/cold instrumentation prints the new fields.

10. **Land a minimal fix** ONLY if Step 2 evidence points to a single dominant cause AND the fix is low-risk (e.g., increase MLflow client timeout, add one retry on connection error). Defer larger fixes to a follow-up.

11. **Update `docs/model-30-serving.md`** with the new failure taxonomy and the log field schema so on-call can read CloudWatch logs without source diving.

---

## 4. Success Criteria

### Functional Requirements

- [ ] **[REQ-F1]** Every error log emitted from the Model 30 inference failure path in `src/api/endpoints/model_serving.py` contains the keys `request_id`, `model_id`, `model_uri`, `model_version`, `phase`, `path_type`, `exception_class`, and `exception_message`. Missing values are logged as the literal string `unknown`, never omitted.
- [ ] **[REQ-F2]** The `phase` field takes exactly one of the values: `artifact_load`, `predict_call`, `response_normalization`, `timeout`, `mlflow_connectivity`. No other values are emitted.
- [ ] **[REQ-F3]** The `path_type` field takes exactly one of `cold` or `warm`, based on whether the model artifact had to be loaded for the current request.
- [ ] **[REQ-F4]** `mlflow_connectivity` and `timeout` phases return HTTP 503. `artifact_load` (when not a connectivity issue), `predict_call`, and `response_normalization` return HTTP 500. The endpoint NEVER returns 200 for a failed inference.
- [ ] **[REQ-F5]** `features/fix-model-30-serving-reliability-failures-challenger/INVESTIGATION.md` exists and attributes each of the 4 CloudWatch failures from the 2026-05-31 24h window to a specific phase, including a quoted log excerpt with request ID for each.
- [ ] **[REQ-F6]** Unit tests exist that simulate at least one failure per phase (5 tests total) by mocking the underlying MLflow / network call to raise a representative exception, and assert both the structured log fields and the HTTP status code.
- [ ] **[REQ-F7]** Unit tests exist verifying `path_type=cold` for the first request to a fresh process and `path_type=warm` for a subsequent request against the same `model_uri`.
- [ ] **[REQ-F8]** `docs/model-30-serving.md` documents the failure phase taxonomy, the log field schema, and the phase → HTTP status mapping.

### Non-Functional Requirements
- [ ] Added instrumentation increases per-request latency by no more than 5 ms on the happy path (verified via the existing `scripts/diagnostics/compare_model_30_vs_21_latency.py`).
- [ ] No new external dependencies introduced (no new packages in `requirements*.txt`).
- [ ] No PII or request payload bodies appear in any new log line.

### Code Quality
- [ ] Follows the structured-logging style established in `src/api/middleware/validation_logging.py` (HOK-1943, commit `7be4cc8`).
- [ ] Type hints present on new functions and the failure-phase enum/literal.
- [ ] No `any` / `Any` types unless justified inline with a `# why:` comment.
- [ ] No lint errors.

---

## 5. Implementation Constraints

- **Code style**: Match the structured-logging shape and naming used in `src/api/middleware/validation_logging.py`. Reuse logger instances; do not introduce a parallel logging framework. Flat keys, no nested JSON.
- **Testing**: Unit tests must mock the MLflow client at the boundary — do NOT spin up a real MLflow server in unit tests. Reuse existing fixtures from `tests/unit/test_model_30_adapter.py`. Integration tests in `tests/integration/test_model_30_mlflow_serving.py` may be updated but must remain runnable in the existing CI workflow (`.github/workflows/model-registration-test.yml`).
- **Security**: Never log request payloads, prediction inputs, or user identifiers other than the existing `request_id`. The `exception_message` field must be truncated to 500 chars to bound log size and prevent accidental payload echoing through exception strings.
- **Performance**: Phase wrapping must not introduce additional MLflow round trips. Adding one try/except per existing MLflow call is acceptable; adding additional calls (e.g., a separate "ping" before predict) is NOT.
- **Backwards compatibility**: The endpoint contract (`POST /api/v1/models/30/predict`) must not change. Response body shape on success is unchanged. On failure, the response body may be enriched with a `phase` field, but the existing keys (`error`, `detail`, etc.) must remain in place.
- **HTTP status mapping**: 503 reserved for transient failures (`mlflow_connectivity`, `timeout`). Do not regress existing 503 behavior on MLflow outages.
- **Scope discipline**: If the evidence-gathering step doesn't surface a clear single root cause, ship the observability/classification changes alone and leave the actual fix for a follow-up ticket. Do not speculatively change MLflow client config.

---

## 6. Validation Steps

### Functional Requirement Validation

**[REQ-F1] Every Model 30 failure log line contains the required structured fields**

Validation scenario:
1. Setup: Run the API service locally with `pytest tests/unit/test_model_serving.py::test_model_30_failure_log_fields -v` (new test).
2. Action: Mock the MLflow client to raise `mlflow.exceptions.MlflowException("artifact missing")`. POST to `/api/v1/models/30/predict` with a valid payload from `data/test_fixtures/model_30_minimal_payload.json`.
3. Expected result: A single ERROR-level log record is captured containing keys: `request_id` (non-empty string), `model_id=30`, `model_uri` (string or `"unknown"`), `model_version` (string or `"unknown"`), `phase` (one of the five enum values), `path_type` (`cold` or `warm`), `exception_class="MlflowException"`, `exception_message` (string, ≤500 chars).
4. Edge cases:
   - `model_uri` not yet resolved (failure during URI lookup) → `model_uri="unknown"`, `model_version="unknown"`, `phase="artifact_load"`.
   - Exception with a 1000-char message → `exception_message` is truncated to 500 chars with trailing ellipsis.

**[REQ-F2] Phase field takes one of exactly five values**

Validation scenario:
1. Setup: New parameterized test `tests/unit/test_model_30_adapter.py::test_phase_classification` with one case per phase.
2. Action: For each phase, mock the corresponding MLflow call to raise a representative exception (e.g., `ConnectionError` for `mlflow_connectivity`, `TimeoutError` for `timeout`, `KeyError` for `response_normalization`).
3. Expected result: The structured log emitted for each case carries the expected `phase` value.
4. Edge cases:
   - Unknown / unmapped exception type → defaults to `phase="predict_call"` (deterministic fallback) and the test asserts this default.
   - Exception raised after `.predict()` returns but before normalization completes → `phase="response_normalization"`.

**[REQ-F3] path_type is cold on first load and warm on subsequent calls**

Validation scenario:
1. Setup: Clear the in-process model cache (instantiate a fresh adapter or call a cache-reset helper).
2. Action: First POST → assert log line shows `path_type="cold"`. Second POST with the same `model_uri` → assert `path_type="warm"`.
3. Expected result: Two distinct log records, one with each value, both within the same test.
4. Edge cases:
   - Different `model_uri` on the second call → `path_type="cold"` for that call.
   - Cache cleared between calls (simulated via cache reset) → `path_type="cold"` again.

**[REQ-F4] HTTP status mapping is correct per phase**

Validation scenario:
1. Setup: Mock each phase's exception in turn.
2. Action: POST `/api/v1/models/30/predict` for each mocked phase using FastAPI's `TestClient`.
3. Expected result:
   - `mlflow_connectivity` → 503
   - `timeout` → 503
   - `artifact_load` (non-connectivity cause) → 500
   - `predict_call` → 500
   - `response_normalization` → 500
4. Edge cases:
   - Happy path (no exception) → 200 with the existing response body shape.
   - `artifact_load` failure caused by `ConnectionError` → classified as `mlflow_connectivity` (not `artifact_load`), returns 503.

**[REQ-F5] Investigation document attributes CloudWatch errors to phases**

Validation scenario:
1. Setup: Pull the 4 error log records from `/ecs/hokusai-api-development` for the 2026-05-31 24h window.
2. Action: Open `features/fix-model-30-serving-reliability-failures-challenger/INVESTIGATION.md`.
3. Expected result: The document lists each of the 4 errors with timestamp, request_id (if available pre-instrumentation), exception class, quoted log excerpt, and an assigned phase classification.
4. Edge cases:
   - Pre-instrumentation logs lack `request_id` → use CloudWatch event ID or timestamp as the identifier and note the limitation.
   - All 4 errors map to the same phase → document this and recommend a specific fix in a follow-up section.

**[REQ-F6] Unit tests exist for all five phases**

Validation scenario:
1. Setup: `pytest tests/unit/test_model_30_adapter.py tests/unit/test_model_serving.py -k "phase" -v`.
2. Action: Run the suite.
3. Expected result: At least 5 tests pass, one per phase. Test names include the phase string (e.g., `test_phase_classification_mlflow_connectivity`).
4. Edge cases:
   - Two tests classify the same exception class differently due to context → both must pass; the differing classification is asserted explicitly.

**[REQ-F7] Cold/warm path tests pass**

Validation scenario:
1. Setup: `pytest tests/unit/test_model_30_adapter.py::test_cold_warm_path -v`.
2. Action: Run the test that exercises two sequential calls.
3. Expected result: First call asserts `path_type="cold"`, second asserts `path_type="warm"`.
4. Edge cases:
   - Cache eviction (if any) between calls → next call is `cold` again; covered by a separate test if eviction is implemented.

**[REQ-F8] docs/model-30-serving.md updated**

Validation scenario:
1. Setup: `git diff docs/model-30-serving.md`.
2. Action: Read the diff.
3. Expected result: A new section "Failure phases" lists the five phase strings, the log field schema (table of field name → type → description), and the phase → HTTP status mapping table.
4. Edge cases: N/A (doc update).

### Input/Output Verification

**Valid Inputs:**
- POST `/api/v1/models/30/predict` with `data/test_fixtures/model_30_minimal_payload.json` (mocked MLflow success) → 200 with existing response shape; no error log emitted.
- POST `/api/v1/models/30/predict` with mocked `MlflowException` on load → 500 (or 503 if connectivity), single ERROR log with `phase="artifact_load"`.

**Invalid Inputs:**
- POST with malformed JSON → 422 (handled by FastAPI / HOK-1943 path, unchanged).
- POST with mocked `requests.exceptions.ConnectionError` from MLflow client → 503, log with `phase="mlflow_connectivity"`.
- POST with mocked `requests.exceptions.Timeout` from MLflow client → 503, log with `phase="timeout"`.
- POST where `.predict()` returns an object missing required keys → 500, log with `phase="response_normalization"`.

### Standard Validation Commands

```bash
# 1. Lint passes
pre-commit run --files src/api/endpoints/model_serving.py src/api/endpoints/model_30_adapter.py
# Expected: no errors

# 2. Type check passes (if mypy is configured for these files)
mypy src/api/endpoints/model_serving.py src/api/endpoints/model_30_adapter.py
# Expected: no type errors (or matches baseline)

# 3. Unit tests pass
pytest tests/unit/test_model_serving.py tests/unit/test_model_30_adapter.py -v
# Expected: all tests pass, including the new phase/path-type tests

# 4. Integration smoke test
pytest tests/integration/test_model_30_mlflow_serving.py -v
# Expected: existing tests still pass

# 5. Diagnostics reproduction (manual; requires dev MLflow reachable)
python scripts/diagnostics/reproduce_model_30_inference.py
# Expected: cold-path run prints path_type=cold; subsequent runs print path_type=warm
```

### Manual Verification Checklist

- [ ] Tail `/ecs/hokusai-api-development` during a forced-failure scenario in dev (e.g., point the adapter at an invalid `model_uri`) and confirm the new structured fields appear in CloudWatch.
- [ ] Confirm `request_id` in the error log matches the `X-Request-ID` response header for the same request.
- [ ] Confirm a happy-path Model 30 call produces no ERROR-level log noise (instrumentation does not over-trigger).
- [ ] Verify `docs/model-30-serving.md` renders correctly (no broken markdown tables).

---

## 7. Definition of Done

- [ ] All success criteria in Section 4 met.
- [ ] All validation steps in Section 6 pass with concrete, measurable outcomes.
- [ ] Each functional requirement [REQ-F1] through [REQ-F8] has a corresponding test or documented manual check.
- [ ] Edge cases listed under each [REQ-Fx] are exercised by tests where applicable.
- [ ] No unrelated changes — diff is bounded to `src/api/endpoints/model_serving.py`, `src/api/endpoints/model_30_adapter.py`, optionally `src/api/endpoints/latency_trace.py`, test files, `INVESTIGATION.md`, and `docs/model-30-serving.md`.
- [ ] Commit message references `HOK-1942`.
- [ ] PR created with a clear description that summarizes the phase classifier, links to `INVESTIGATION.md`, and quotes one representative CloudWatch log line.

---

## 8. Rollback Plan

- The change is purely additive (new logging, new exception wrapping). To rollback: `git revert <sha>` on the merge commit and redeploy the API service.
- No database migrations, no schema changes, no feature flags required.
- If the new try/except layering surfaces a previously-swallowed exception type that now reaches the client, rollback restores prior behavior immediately; the structured logs collected before rollback still inform the follow-up investigation.

---

## 9. Release Readiness

- **database_change_risk**: none
- **env_changes**: none
- **config_changes**: none
- **manual_steps**: none

---

## 10. Proposed Labels

**Risk Level**:

**Selected**: `Risk: Medium`

**Justification**: Medium — touches a live user-facing serving endpoint (Model 30 predict) and changes the HTTP status / log shape on error paths. Additive instrumentation but exercising the failure path requires careful unit coverage. Not Low (production-facing endpoint behavior change), not High (no schema, no auth, no infra change).

---

**Files to Modify**:
- `src/api/endpoints/model_serving.py`
- `src/api/endpoints/model_30_adapter.py`
- `src/api/endpoints/latency_trace.py`
- `tests/unit/test_model_serving.py`
- `tests/unit/test_model_30_adapter.py`

**Label**: `Files: model_serving.py, model_30_adapter.py, latency_trace.py, test_model_serving.py, test_model_30_adapter.py`

**Purpose**: Prevents parallel tasks from modifying the same Model 30 serving files.

---

**Architectural Layer**:

**Selected**: `Layer: API`

**Purpose**: Endpoint-layer change; can run in parallel with Database, Infra, or unrelated Service tasks.

---

**Area**:

**Selected**: `Area: Model-Serving`

**Purpose**: Avoid concurrent tasks editing the Model 30 serving path (e.g., HOK-1943 follow-ups).

---

**Test Coverage**:

**Selected**: `Tests: Unit`

**Purpose**: Primary coverage is unit-level (mocked MLflow); existing integration tests are only re-run, not expanded.

---

**Component**:

**Selected**: `Component: Model30-TechnicalTaskRouter`

**Purpose**: Avoid conflict with other Model 30 / Technical Task Router tasks.

---

### Label Summary

```
Suggested labels for this task:
- Risk: Medium
- Files: model_serving.py, model_30_adapter.py, latency_trace.py, test_model_serving.py, test_model_30_adapter.py
- Layer: API
- Area: Model-Serving
- Tests: Unit
- Component: Model30-TechnicalTaskRouter
```

**How these labels help the autonomous workflow:**
- **Risk: Medium** — Max 2 Medium risk tasks can run in parallel.
- **Files: ...** — Prevents file conflicts with HOK-1943 follow-ups and other Model 30 work.
- **Layer: API** — Can run in parallel with Service/Database/Infra tasks.
- **Area: Model-Serving** — Prevents conflicts with other Model 30 serving-path tasks.
- **Tests: Unit** — Can run in parallel with other Unit-test tasks.
- **Component: Model30-TechnicalTaskRouter** — Prevents conflicts with other Technical Task Router tasks.