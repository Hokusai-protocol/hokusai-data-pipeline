# HOK-1869 — Model 30 Cold-Start and Serving Reliability Summary

## Identification

| Field | Value |
|-------|-------|
| Issue | HOK-1869 |
| Branch | `task/model-30-performance-cold-start-and-serving-reliability` |
| Base branch | `auto/integration` |
| Commit SHA (coding start) | `18d549b5ddb90dabdef92c6624933f71ec254463` |
| Date | 2026-06-03 |
| Environment | Development (`hokusai-development` ECS cluster) |
| Related issues | HOK-1874 (warmup contract), HOK-1875 (latency budget) |

## Budget Snapshot (from `configs/model_30_budget.yaml`)

| Metric | Soft | Hard |
|--------|------|------|
| `cold_readiness_ms` | 30,000 ms | 60,000 ms |
| `artifact_load_ms` | 15,000 ms | 25,000 ms |
| `warm_p50_ms` | 300 ms | 600 ms |
| `warm_p95_ms` | 800 ms | 1,500 ms |
| `warm_p99_ms` | 1,500 ms | 3,000 ms |
| `timeout_rate` | 0.0 | 0.02 |
| `warm_memory_mb` | 800 MB | 1,200 MB |
| `cold_memory_mb` | 1,200 MB | 1,800 MB |

## Code Defect Found and Fixed

### Bug: Smoke Checker Sent Wrong Payload Format

**File:** `scripts/model_30/latency_smoke_check.py` — `_run_warm_requests()`

**Description:** The smoke checker loaded the curated fixture (`data/test_fixtures/model_30_curated_payload.json`) and posted it directly as the HTTP request body. The API's `PredictionRequest` schema requires `{"inputs": <fixture>}` at the top level. Posting the fixture bare (without wrapping) caused FastAPI to return a 422 validation error (`inputs` field required) on every warm request. The 422 Pydantic error body (a list, not a Model 30 error string) was classified as `infra_upstream` by `classify_response`, resulting in 100% `infra_upstream` rate → `infra_inconclusive` result instead of meaningful warm-path measurements.

**Fix applied:**
```python
# Before (wrong — sends fixture directly, gets 422)
response = session.post(predict_url, json=payload, timeout=30)

# After (correct — wraps fixture as inputs)
response = session.post(predict_url, json={"inputs": payload}, timeout=30)
```

**Test added:** `tests/unit/test_model_30_latency_budget.py::test_run_warm_requests_wraps_fixture_as_inputs` — verifies the POST body is `{"inputs": <fixture>}`.

**Scope classification:** "latency smoke reporting misclassifies Model 30 errors or omits required evidence" (per scoped fix policy).

## Phase 2: Local Contract Validation

All targeted unit tests pass on commit `18d549b`:

```
tests/unit/test_model_30_adapter.py             PASS
tests/unit/test_model_30_warmup.py              PASS
tests/unit/test_api_startup_prewarm.py          PASS
tests/unit/test_ready_endpoint_model_30.py      PASS
tests/unit/test_model_30_latency_budget.py      PASS (108 total, +1 new test)
tests/unit/test_model_30_latency_trace.py       PASS
tests/integration/test_model_30_mlflow_serving.py  SKIPPED (MLFLOW_TRACKING_URI not set)
```

Ruff check on modified files: **PASS** (no new errors introduced; pre-existing `health.py` annotations are unchanged).

## Phase 3: Deployed Cold-Start Capture — INCONCLUSIVE

**Blocking condition:** `MODEL_30_SMOKE_JWT` environment variable is not set in the current execution environment. AWS credentials are also not available, so `aws ecs update-service --force-new-deployment` cannot be triggered.

**What would be measured if environment were available:**
- ECS task start timestamp
- First `/healthz` or `/health` 200
- First `/ready` returning 503 while `model_30.state=warming`
- First `/ready` returning 200 with `model_30.warmed=true`
- First authenticated `/api/v1/models/30/predict` 200
- Compare `cold_readiness_ms` and `artifact_load_ms` to budget thresholds

**Manual steps required (post-review):**
1. Set `MODEL_30_SMOKE_JWT` to a valid development API token
2. Force `aws ecs update-service --cluster hokusai-development --service hokusai-api-development --force-new-deployment`
3. Poll CloudWatch logs `/ecs/hokusai-api-development` for `model_30_warm_started` and `model_30_warm_completed` events
4. Capture timestamps, compute `cold_readiness_ms` and `artifact_load_ms`
5. Run smoke check (see Phase 4)

## Phase 4: Warm-Path and Reliability Evidence — INCONCLUSIVE

**Blocking condition:** Same as Phase 3 — no JWT and no reachable development API.

**Smoke check command (to be run after Phase 3):**
```bash
export MODEL_30_SMOKE_JWT=<development-token>
python scripts/model_30/latency_smoke_check.py \
  --api-url https://api.hokus.ai \
  --warmup-timeout-s 90 \
  --num-requests 50 \
  --budget-file configs/model_30_budget.yaml \
  --report-out features/model-30-performance-cold-start-and-serving-reliability/model_30_smoke_report.json
```

**Expected pass criteria:**
- 0 Model 30-specific 5xx/503/504 errors in the warm smoke run
- `timeout_rate` ≤ 0.02 (hard budget)
- p50/p95/p99 within hard thresholds (600/1500/3000 ms)
- No `model_30_error` classifications against the curated valid payload

**Reliability sweep:** The smoke checker runs 50 sequential requests using the curated fixture repeated through the warm path. This explicitly documents that coverage is the canonical curated object repeated rather than a true multi-payload corpus. Per plan, this is acceptable for the smoke gate.

## Phase 5: Readiness Behavior Observed

Static code review of the serving path confirms the following behaviors (no live observation possible):

| Scenario | `/ready` status | `can_serve_traffic` | Model 30 predict gate |
|----------|----------------|---------------------|-----------------------|
| `state=warming` + prewarm enabled | 503 | False | 503 from gate |
| `state=failed` + prewarm enabled | 200 (degraded) | True | 503 from gate |
| `state=warmed` | 200 | True | Allowed |
| `state=not_started` + prewarm disabled | 200 | True | Allowed (cold path) |

No readiness-reports-ready-before-cache bug was found. The `/ready` endpoint sets `can_serve_traffic=False` while `state=warming` and prewarm is enabled, and only returns 200 with `model_30.warmed=true` after `warm_model_30()` completes, which stores the artifact in `_MODEL_30_CACHE` before setting the state.

No predict-path unclassified-500 bug was found. Model 30 inference failures are classified as `TIMEOUT` (504), `ARTIFACT_LOAD` (503), `PREDICT_CALL` (503), `RESPONSE_NORMALIZATION` (503), or `MLFLOW_CONNECTIVITY` (503). Concurrent cold-load races raise `Model30LoadInProgressError` → 503.

## REQ Verdicts

| Requirement | Verdict | Notes |
|-------------|---------|-------|
| REQ-F1: Cold-start completes within budget | INCONCLUSIVE | No JWT / ECS access to measure; code path is correct |
| REQ-F2: Warm p50/p95/p99 within hard thresholds | INCONCLUSIVE | No live API to run smoke check |
| REQ-F3: Timeout rate ≤ 0.02 | INCONCLUSIVE | No live API to measure |
| REQ-F4: Readiness gate blocks traffic correctly during warmup | PASS | Code review confirms correct 503 behavior while warming |
| REQ-F5: 0 Model 30-specific 5xx against curated valid payload | INCONCLUSIVE | Smoke check cannot be run without JWT |

## Follow-Up

- **HOK-1869 smoke check must be re-run** with `MODEL_30_SMOKE_JWT` set against `hokusai-api-development` after a forced redeployment to collect cold-start and warm-path evidence.
- **HOK-1874** (warmup contract) and **HOK-1875** (latency budget) are upstream; this task does not redesign those systems.
- The payload-wrapping fix in the smoke checker is prerequisite for any future `model_30_smoke_check.py` run to produce valid results.

## Commit

The only code changes in this coding phase are:
- `scripts/model_30/latency_smoke_check.py`: wrap fixture in `{"inputs": ...}` for POST request
- `tests/unit/test_model_30_latency_budget.py`: `test_run_warm_requests_wraps_fixture_as_inputs`
