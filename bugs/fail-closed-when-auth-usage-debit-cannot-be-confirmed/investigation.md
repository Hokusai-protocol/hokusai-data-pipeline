# HOK-2758 Investigation

## Bug Summary

`POST /api/v1/models/30/predict` can execute inference even when the auth-service cannot confirm the pre-request usage debit. Linear records 22 predictions for one opaque API-key ID on 2026-08-12 through 2026-08-13 where every debit returned `500 Internal Server Error` with one attempt and the prediction handler still ran. This is a priority-1 revenue-integrity incident: authenticated callers can receive billable inference without a confirmed charge whenever debit processing fails.

The affected population is any caller of a request currently subject to the auth middleware's debit path. Model 30 is the observed and explicitly required containment target. Free contribution ingestion and MLflow registry administration are intentionally outside the debit path.

## Reproduction Steps

1. Build a FastAPI test application with `APIKeyAuthMiddleware` and the model-serving router, following `tests/unit/test_model_serving_auth.py`.
2. Return a valid `ValidationResult` containing a `key_id` from `validate_with_auth_service()`.
3. Make `POST /api/v1/usage/{key_id}/debit` return 500, or raise `httpx.ConnectError`/`httpx.TimeoutException`.
4. POST a valid request to `/api/v1/models/30/predict` and spy on `serving_service.serve_prediction`.
5. Current result: `_debit_usage()` returns `"error"`; `dispatch()` does not branch on that result; the model handler runs.
6. Fixed result: the API returns a client-safe 503 with retry guidance and a request ID, and `serve_prediction` is not awaited.

The current unit suite codifies the defect directly in `test_dispatch_fails_open_when_debit_returns_error` and in the StopIteration regression test.

## Affected Components

- `src/middleware/auth.py`
  - `dispatch()` performs validation, preserves contribution and registry bypasses, awaits `_debit_usage()`, and currently handles only `"rejected"`.
  - `_debit_usage()` returns `"accepted"` for a response below 300, `"rejected"` for 402, and `"error"` for every other HTTP or transport outcome.
  - A broad `except Exception` in `dispatch()` converts unexpected debit exceptions to `"error"` and deliberately continues downstream.
  - A valid auth result with no `key_id` skips debit entirely and currently continues downstream; for a billable prediction this is also an unconfirmed debit.
- `tests/unit/test_middleware/test_auth_middleware_billing.py`
  - Covers debit result classification, retry behavior, structured rejection handling, contribution bypasses, and the current fail-open dispatch contract.
- `tests/unit/test_middleware/test_auth_middleware_stopiteration.py`
  - Verifies an unexpected debit exception does not produce a generic 500 by asserting the downstream handler still runs. It must be retained but changed to expect the controlled 503 containment response.
- `tests/unit/test_model_serving_auth.py`
  - Provides the closest route-level FastAPI/TestClient harness with the real middleware and model-serving router. It is the appropriate place to prove Model 30's handler is not called for debit 500 and transport failures.
- `src/api/middleware/validation_logging.py`
  - `get_or_generate_request_id()` already bounds incoming IDs, creates a UUID when absent, and stores it on `request.state`; reuse avoids a second request-ID implementation.
- `docs/model-30-serving.md`
  - Documents only the 402 debit-rejection contract and should be extended with the retryable 503 fail-closed contract.

No database schema, migration, model-serving implementation, or contribution service change is required.

## Initial Observations

- `dispatch()` calls debit before `call_next()`, so the containment point already precedes request parsing and inference. No downstream rollback is needed.
- `_debit_usage()` already distinguishes the only three decisions required by dispatch: confirmed 2xx, confirmed 402, and unconfirmed/failed debit. The smallest safe fix is to treat every outcome other than `"accepted"` or `"rejected"` as unavailable and return 503.
- The contribution bypass at `POST /api/v1/models/{model_id}/contributions[/]` returns before debit and should remain in the same order.
- Registry requests are already excluded from balance enforcement and debit. The fix should not alter that eligibility decision.
- The existing success check is `status_code < 300`; the required contract is explicitly 2xx, so it should be tightened to `200 <= status_code < 300`.
- Non-402 4xx responses already become `"error"`; the bug is that dispatch ignores that result. Mapping them to the same client-safe 503 prevents upstream 404/409 validation or invariant failures from becoming billing bypasses and avoids exposing auth-service internals.
- Failure HTTP logs include key ID, model ID, endpoint, and idempotency key but omit request ID and a normalized outcome. Transport logs are unstructured. The 402 log omits key ID and idempotency key. Confirmed 2xx has no outcome log.
- `dispatch()` currently reads only an incoming `x-request-id`; when absent, debit logs receive `None`. A request ID must be resolved before debit and reused in the response/log context.
- `_debit_usage()` defaults to one attempt. HOK-2758 is immediate containment, so retry-policy changes are not required and would add latency and ambiguity.

## Data Analysis Required

Before deployment, use the existing `usage_debit_failure` and `usage_debit_retry_exhausted` records to establish the recent rate of debit failures by `status_code`, `model_id`, and opaque `key_id`. Do not query or log bearer tokens.

After deployment, correlate debit outcome records and API access logs by request ID and verify:

- every failed/unconfirmed Model 30 debit corresponds to a 503, not a 2xx prediction;
- confirmed 402 results preserve the existing structured response;
- the count of `accepted` debit outcomes matches served billable predictions for the observation window;
- contribution ingestion remains successful and produces no debit call.

## Investigation Strategy

1. Lock the response contract with middleware unit tests before changing control flow.
2. Change dispatch so a downstream handler is reachable only after `"accepted"` for a debit-eligible request; preserve the dedicated 402 branch.
3. Convert unexpected debit exceptions and missing `key_id` on billable prediction routes into the same controlled 503 path.
4. Normalize debit observability fields across accepted, rejected, HTTP failure, and transport failure outcomes.
5. Add FastAPI route-level tests that drive `/api/v1/models/30/predict` through the real middleware and assert the serving spy is untouched for 500 and transport failures.
6. Run the focused middleware/model-serving test files, then the broader unit suite.

Success means the only path from a debit-eligible request to `call_next()` is a confirmed 2xx outcome, while 402 and contribution contracts remain unchanged.

## Risk Assessment

- Revenue integrity: critical until containment is deployed; current behavior serves unbilled inference.
- Availability: fail-closed deliberately converts auth-service debit outages into prediction 503s. The response must be retryable and must not claim the API key is invalid.
- Double billing: clients will retry 503s, so the same idempotency key must be retained across any internal retry attempts. Cross-request retry idempotency is unchanged by this issue and should not be redesigned here.
- Scope regression: changing which routes are debit-eligible could bill free traffic or block administrative traffic. Preserve the existing contribution and registry boundaries; add a missing-key guard specifically where a debit is required.
- Information exposure: never return upstream bodies or exception text to clients and never log the submitted API key. Opaque `key_id` is required and acceptable.
- Latency: do not add retries in the immediate fix; the debit already blocks inference.

## Timeline

- 2026-08-12 through 2026-08-13: 22 correlated Model 30 predictions were served after debit 500 responses for one opaque key ID.
- 2026-08-14: HOK-2758 was created as a priority-1 backlog issue.
- Current repository state: the fail-open behavior remains in `dispatch()` and is explicitly asserted by unit tests.

## Baseline Verification

The focused command collected 75 tests across the billing middleware, StopIteration regression, and model-serving auth files. It reported 73 passing and two pre-existing stale assertions unrelated to HOK-2758:

- `test_validate_logs_attribution_on_upstream_schema_error` expects no `error_type`, while production code returns `error_type="unavailable"`.
- `test_auth_timeout_handling` expects 401, while production code correctly returns retryable 503 for auth validation timeout.

The repository-wide 80% coverage gate also fails when only these focused files run. Implementation validation should update or separately reconcile those stale assertions, or run the project-approved broader command that satisfies the coverage gate.
