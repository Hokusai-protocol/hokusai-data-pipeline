# HOK-1869 Implementation Plan

## Planning Artifacts

- Expanded task packet: `features/model-30-performance-cold-start-and-serving-reliability/task-packet.md`
- Post-expansion route: `features/model-30-performance-cold-start-and-serving-reliability/.post-expansion-route.json`
- Migration detection: no marker needed. The task packet explicitly states "No data migrations" and `database_change_risk: none`.
- Router note: routing used heuristic fallback because the remote Hokusai router path reported missing auth, but JSON routing output was saved successfully.

## Objective

Close the Model 30 cold-start and serving reliability rollup by proving that the deployed development API can serve valid Model 30 predictions within the existing budget and by fixing only small residual serving-path defects discovered during validation.

The coding phase should treat this as verification-led work. HOK-1874 and HOK-1875 have already implemented the warmup contract and latency budget; this task should not redesign those systems or loosen thresholds.

## Current Codebase Findings

- `configs/model_30_budget.yaml` is the canonical budget. It defines hard and soft thresholds for `cold_readiness_ms`, `artifact_load_ms`, `warm_p50_ms`, `warm_p95_ms`, `warm_p99_ms`, `timeout_rate`, `warm_memory_mb`, and `cold_memory_mb`.
- `src/api/main.py` configures MLflow transport on startup, verifies registered MLflow models, then schedules `_startup_warm_model_30()` as a background task when `model_30_prewarm_enabled` is true.
- `src/api/endpoints/model_30_adapter.py` owns the process-local model cache, warmup state, warm fixture loading, artifact load, predict call, output normalization, and structured failure phases.
- `src/api/routes/health.py` exposes `/ready` with a `model_30` payload and returns 503 while prewarm is enabled and the model is still warming or not started. A failed warmup returns degraded 200, matching the current documented rollback behavior.
- `src/api/endpoints/model_serving.py` gates Model 30 predictions while warmup is in progress, emits a single `model_30_latency_trace`, classifies timeout/load/normalization failures, and returns 422 for request-contract validation errors.
- `scripts/model_30/latency_smoke_check.py` already polls `/ready`, sends 50 sequential warm requests, writes a JSON report, evaluates the budget, and classifies infra/auth/network issues separately from Model 30 errors.
- `.github/workflows/model-30-latency-check.yml` builds linux/amd64 API and MLflow images, seeds MLflow, runs the smoke checker, captures memory, uploads `model_30_smoke_report.json`, and gates on the report.
- `data/test_fixtures/model_30_curated_payload.json` is currently a single valid payload object, not a corpus/list. The coding phase should not assume it can iterate a payload set unless it adds a compatible helper or derives variants.

## Implementation Phases

### 1. Baseline Audit

1. Record the commit SHA and branch at the start of coding.
2. Re-read these files before editing because Model 30 serving files have high churn:
   - `src/api/endpoints/model_30_adapter.py`
   - `src/api/endpoints/model_serving.py`
   - `src/api/routes/health.py`
   - `src/api/main.py`
   - `scripts/model_30/latency_smoke_check.py`
   - `.github/workflows/model-30-latency-check.yml`
   - `configs/model_30_budget.yaml`
3. Confirm the warmup, readiness, and budget behavior still matches the expanded task packet.
4. Do not change `configs/model_30_budget.yaml` unless the implementation has a clear bug in how existing thresholds are read or reported. Budget values are out of scope.

### 2. Local Contract Validation

Run focused local checks before touching code:

- `pytest tests/unit/test_model_30_adapter.py tests/unit/test_model_30_warmup.py tests/unit/test_api_startup_prewarm.py tests/unit/test_ready_endpoint_model_30.py tests/unit/test_model_30_latency_budget.py tests/unit/test_model_30_latency_trace.py -v`
- `pytest tests/integration/test_model_30_mlflow_serving.py -v` only when the required MLflow environment is available, otherwise record it as skipped/not runnable.
- `ruff check` on changed Python files and nearby Model 30 files, using the repo's configured command.

If these fail before any edits, classify each failure:

- Serving-path bug in this task: fix narrowly.
- Existing infrastructure/auth/MLflow availability issue: document in `SUMMARY.md` and do not mask as a pass.
- Scope owned by HOK-1874 or HOK-1875: document and reopen/link the appropriate sub-task rather than absorbing a redesign here.

### 3. Deployed Cold-Start Capture

1. Ensure a valid development JWT is available through `MODEL_30_SMOKE_JWT`; never commit the token.
2. Force a fresh development API deployment using the standard deployment path or ECS force-new-deployment for `hokusai-api-development`.
3. Build or deploy images with `--platform linux/amd64` if a Docker build is involved.
4. Capture timestamps:
   - ECS task start
   - first `/healthz` or lightweight health 200
   - first `/ready` 503 showing Model 30 warming, if observable
   - first `/ready` 200 with `model_30.warmed=true`
   - first authenticated `/api/v1/models/30/predict` 200
5. Compare `cold_readiness_ms` and `artifact_load_ms` to `configs/model_30_budget.yaml`.
6. Preserve raw response snippets and timings in the feature summary. Include failure body and CloudWatch/log references for any 5xx, timeout, or warmup failure.

### 4. Warm-Path and Reliability Evidence

1. Run the existing smoke checker against the warmed service:
   - `python scripts/model_30/latency_smoke_check.py --api-url https://api.hokus.ai --warmup-timeout-s 90 --num-requests 50 --budget-file configs/model_30_budget.yaml --report-out features/model-30-performance-cold-start-and-serving-reliability/model_30_smoke_report.json`
2. If the script requires a different deployed URL or auth env var, use its actual CLI and record the invocation in the summary.
3. Compute p50/p95/p99 from successful samples and confirm all hard thresholds pass.
4. For reliability, use the current curated fixture as the canonical valid payload. Because it is a single object, either:
   - extend the validation harness to run a deterministic set of valid variants generated from the same public contract, or
   - explicitly document that the reliability sweep covered the canonical curated object repeated through the smoke checker rather than a true corpus.
5. Required pass bar for the evidence:
   - 0 Model 30-specific 5xx/503/504 errors in the warm smoke run.
   - `timeout_rate` at or below the hard budget.
   - any 4xx must be deterministic and tied to an intentionally invalid request-contract check, not to the curated valid payload.

### 5. Scoped Fix Policy

Only patch code if validation reveals a small, clear, Model-30-specific reliability defect. Examples that are in scope:

- readiness reports traffic-ready before the warm cache is actually populated;
- predict path returns an unclassified 500 where an existing 503/504/422 contract should apply;
- warmup leaves stale or contradictory state after timeout/failure;
- latency smoke reporting misclassifies Model 30 errors or omits required evidence;
- a race allows concurrent cold requests to bypass the load-in-progress guard.

Out of scope for this task:

- changing public request/response schemas;
- loosening latency thresholds;
- changing the warmup architecture;
- model retraining, MLflow registry promotion, or runtime replacement;
- infrastructure edits outside this repo.

For any scoped code change, add or strengthen the closest existing unit/integration test. Prefer extending existing test files over adding a new test surface.

### 6. Summary Report

Create `features/model-30-performance-cold-start-and-serving-reliability/SUMMARY.md` with:

- issue ID, branch, measured commit SHA, date/time, and environment;
- budget snapshot copied from `configs/model_30_budget.yaml`;
- cold-start timeline and verdict;
- warm smoke metrics and verdict;
- reliability sweep status, sample count, success count, non-200 classifications, and timeout rate;
- `/ready` behavior observed during cold start;
- links/references to HOK-1874 and HOK-1875;
- any follow-up issues opened or recommended;
- explicit PASS/FAIL/INCONCLUSIVE verdict for REQ-F1 through REQ-F5.

Do not mark the rollup complete if any required verdict is FAIL. If external infrastructure blocks measurement, use INCONCLUSIVE and state exactly what is missing.

### 7. Final Verification for Coding Phase

Before handing to review, run or record why unable:

- Focused unit tests listed in Phase 2.
- Integration test with live MLflow if environment is available.
- `python scripts/model_30/latency_smoke_check.py ...` against the target environment.
- `.github/workflows/model-30-latency-check.yml` in CI or workflow_dispatch if path filters skip it.
- Repo lint command for modified Python files.

## Edge Cases and Error Handling

- Missing `MODEL_30_SMOKE_JWT`: smoke checker returns `infra_inconclusive`; do not treat this as a serving pass.
- `/ready` never warms within timeout: fail cold-start/readiness verification and inspect `model_30.last_error`, structured `model_30_warm_failed` logs, and MLflow connectivity.
- `/ready` returns degraded 200 with `model_30.state=failed`: document as degraded mode; Model 30 rollup should remain failed unless a deliberate rollback is being tested.
- Warm p95/p99 exceeds hard budget while p50 passes: fail the rollup; all configured hard percentile thresholds are gates.
- Any 5xx from the curated valid payload: fail reliability and preserve the payload, response body, request ID, and matching `model_30_inference_failure` log.
- Auth 401/403 or upstream 502 from the deployed service: classify as infra/auth unless the response body matches Model 30 failure prefixes.
- Curated fixture shape mismatch: keep `PredictionRequest.inputs` contract in mind. The fixture file contains the `inputs` object, while API calls must wrap it as `{"inputs": <fixture>}`.

## Architectural Decisions

- Use the existing smoke checker as the primary measurement tool instead of adding a parallel benchmark stack. It already enforces the canonical budget and emits machine-readable evidence.
- Keep readiness and predict-path behavior aligned with existing docs: prewarm-enabled warming blocks traffic with 503; failed warmup is degraded 200 but not a successful Model 30 rollup.
- Keep all performance thresholds in `configs/model_30_budget.yaml`; summary reports may quote values but must not become a second source of truth.
- Add code only for defects found by validation. The expected main diff is `SUMMARY.md` plus possibly a narrow fix and tests.

## Likely Files to Modify in Coding Phase

Expected:

- `features/model-30-performance-cold-start-and-serving-reliability/SUMMARY.md`

Possible if validation exposes a defect:

- `src/api/endpoints/model_30_adapter.py`
- `src/api/endpoints/model_serving.py`
- `src/api/routes/health.py`
- `scripts/model_30/latency_smoke_check.py`
- existing focused tests under `tests/unit/` or `tests/integration/`
- `docs/model-30-serving.md` only if an operational note must be corrected

Avoid modifying:

- `configs/model_30_budget.yaml` unless budget parsing/reporting is defective;
- public schemas unless a separate approved contract task exists;
- infrastructure or deployment repositories.

## Release Readiness

- `database_change_risk`: none
- `env_changes`: none expected; existing `MODEL_30_SMOKE_JWT`, `MODEL_30_MLFLOW_URI`, `MLFLOW_TRACKING_URI`, `MODEL_30_PREWARM_ENABLED`, `MODEL_30_WARM_TIMEOUT_S`, `MODEL_SERVING_PREDICTION_TIMEOUT_SECONDS`, `MODEL_30_READINESS_TIMEOUT_SECONDS` may be used but should not need new values
- `config_changes`: none expected
- `manual_steps`: force fresh development API deployment for cold-start measurement, provide valid development JWT for smoke check, verify CI latency workflow or trigger workflow_dispatch if PR path filters skip it

## Approval Gate

After approval, create:

`features/model-30-performance-cold-start-and-serving-reliability/.plan-approved`

Then stop so the orchestrator can launch the coding phase.
