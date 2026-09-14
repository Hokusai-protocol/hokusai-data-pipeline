# HOK-2758 Fix Plan

## Execution Status

Implementation, focused regression coverage, documentation, and local validation are complete. Production deployment and post-deployment CloudWatch reconciliation remain operational follow-up steps. See `validation.md` for commands and results.

## 1. Define the fail-closed response and debit decision contract

1. [ ] In `src/middleware/auth.py`, define one client-safe retryable response for any unconfirmed debit: HTTP 503, `Retry-After`, `X-Request-ID`, and a stable machine-readable error such as `usage_debit_unavailable`.
   a. [ ] Do not include the auth-service response body, exception text, URL, bearer token, or other secrets.
   b. [ ] Keep the existing 402 body exactly as `{error, reason, reason_code}`.
   c. [ ] Treat only `200 <= status_code < 300` as a confirmed debit.
2. [ ] Resolve and store a bounded request ID before debit using the existing `get_or_generate_request_id()` behavior so generated IDs are present in failure logs and response headers even when the client sends no ID.
3. [ ] Preserve the existing debit eligibility boundary for immediate containment: contribution ingestion returns before debit, and MLflow registry administration remains excluded. Do not redesign billing scope or retry policy in this fix.
4. [ ] For a billable prediction whose validated auth context has no `key_id`, return the same 503 without invoking `_debit_usage()` or the downstream handler.

## 2. Make middleware dispatch fail closed

1. [ ] Update `APIKeyAuthMiddleware.dispatch()` so debit outcomes have exhaustive control flow:
   a. [ ] `accepted`: continue to `call_next(request)`.
   b. [ ] `rejected`: return the existing structured 402.
   c. [ ] `error` or any unknown outcome: return the new retryable 503.
2. [ ] Change the broad exception guard around `_debit_usage()` to log the controlled failure and return the same 503; retain protection against coroutine-boundary errors without serving the request.
3. [ ] Keep `call_next()` textually and logically unreachable for a debit-eligible request unless the debit result is confirmed 2xx.
4. [ ] Leave `max_retries=1` and the existing idempotency key stable across internal attempts. Retry tuning and cross-request idempotency are separate concerns.

## 3. Normalize debit observability

1. [ ] Emit a structured debit outcome record for accepted, rejected, non-402 4xx, 5xx, transport/timeout, and unexpected-exception paths.
2. [ ] Include the same safe correlation fields on each outcome: normalized `outcome`, opaque `key_id`, `model_id`, `idempotency_key`, `request_id`, endpoint, upstream status when available, and attempt count.
3. [ ] Add `key_id` and `idempotency_key` to the existing 402 record and add `request_id` to existing HTTP failure/retry-exhausted records.
4. [ ] Convert the transport failure message from interpolated text to structured fields. Keep response-body truncation for diagnostics, but never return that body to the client.
5. [ ] Preserve existing Sentry rejection context and CloudWatch `UsageDebitRejected` behavior. If a new metric is added for unavailable debits, use a distinct name such as `UsageDebitUnavailable` rather than counting service failures as insufficient balance.

## 4. Reverse and extend middleware regression tests

1. [ ] In `tests/unit/test_middleware/test_auth_middleware_billing.py`, replace `test_dispatch_fails_open_when_debit_returns_error` with a fail-closed assertion: 503 response, retry headers, stable error body, and `call_next.assert_not_awaited()`.
2. [ ] Add or parameterize dispatch tests for `_debit_usage()` outcomes from non-402 4xx values (at minimum 404 and 409) and 5xx values.
3. [ ] Retain tests proving 200/other 2xx proceeds and 402 preserves its current status/body and never calls downstream.
4. [ ] Add the missing-`key_id` billable prediction case.
5. [ ] Tighten `_debit_usage()` classification tests so 1xx/3xx/non-402 4xx/5xx and transport/timeout return `"error"`, while only 2xx returns `"accepted"`.
6. [ ] Assert common structured log fields for success, rejection, HTTP error, transport error, and unexpected exception, including generated and caller-provided request IDs; assert the raw API key never appears.
7. [ ] Keep all existing contribution tests proving exact POST path variants bypass debit, preserve auth state, and proceed even with zero/negative balance. Keep tests proving near-match paths do not bypass.
8. [ ] In `tests/unit/test_middleware/test_auth_middleware_stopiteration.py`, reverse the historical fail-open assertion: unexpected debit `RuntimeError` must produce the controlled 503 and must not call downstream.

## 5. Add route-level Model 30 containment tests

1. [ ] Extend `tests/unit/test_model_serving_auth.py` using its real FastAPI middleware/router harness.
2. [ ] Stub auth validation to a valid result, spy on `src.api.endpoints.model_serving.serving_service.serve_prediction`, and drive `/api/v1/models/30/predict` through `TestClient`.
3. [ ] For an auth debit HTTP 500, assert a retryable 503 and `serve_prediction.assert_not_awaited()`.
4. [ ] For `httpx.ConnectError` and `httpx.TimeoutException`, assert the same response and untouched serving spy.
5. [ ] Add a route-level successful 2xx control showing the same Model 30 request reaches the handler.
6. [ ] Keep contribution coverage at the middleware boundary; add a real-router contribution test only if the TestClient harness reveals middleware ordering or dependency behavior not covered by the existing exact-path tests.

## 6. Documentation and operational verification

1. [ ] Update `docs/model-30-serving.md` next to “Usage Debit Rejection” with the 503 response contract, retry semantics, request-ID header, and the guarantee that inference is not invoked.
2. [ ] Document that 402 means a confirmed insufficient-funds rejection, while 503 means the charge could not be confirmed and the request is safe to retry.
3. [ ] Add a CloudWatch Logs Insights query or runbook note that correlates debit outcomes with API responses by request ID and groups unavailable outcomes by model ID and upstream status.
4. [ ] After deployment, verify failed debits produce 503s and no Model 30 inference logs for the same request IDs; verify accepted debit counts reconcile with served predictions.
5. [ ] Confirm contribution ingestion continues without debit records and that the existing 402 client contract is unchanged.

## 7. Validation sequence

1. [ ] Run the focused tests while iterating:

   ```bash
   pytest tests/unit/test_middleware/test_auth_middleware_billing.py \
     tests/unit/test_middleware/test_auth_middleware_stopiteration.py \
     tests/unit/test_model_serving_auth.py --no-cov -q
   ```

2. [ ] Reconcile the two known stale baseline assertions in these files if they remain on the implementation branch: auth validation schema-error results now carry `error_type="unavailable"`, and auth validation timeout correctly returns 503 rather than 401.
3. [ ] Run the repository's full unit/CI command so the global 80% coverage gate is evaluated with the intended suite rather than only the three focused files.
4. [ ] Run Ruff on the changed Python files and validate Markdown/JSON formatting.
5. [ ] Perform a local smoke request for Model 30 with mocked debit 2xx, 402, 404/409, 500, and transport failure and record status, handler call count, and correlation log fields.

## Definition of Done

- [ ] No debit-eligible prediction reaches the handler without a confirmed 2xx debit.
- [ ] 402 retains its current structured response and never invokes inference.
- [ ] 5xx, timeout/connection failure, unexpected debit exception, non-402 4xx, and missing debit identity return a client-safe retryable 503 and never invoke inference.
- [ ] Free contribution ingestion and registry exclusions remain unchanged.
- [ ] Every debit outcome is observable with outcome, opaque key ID, model ID, idempotency key, and request ID, with no API-key secret in logs or responses.
- [ ] Route-level tests prove Model 30 inference is not called for HTTP 500 and transport failures.
- [ ] Focused and full validation pass, with the two known stale baseline assertions either corrected in scope or explicitly separated from HOK-2758.
