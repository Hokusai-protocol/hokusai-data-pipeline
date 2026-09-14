# HOK-2758 Validation

## Implemented Contract

- Debit-eligible requests reach downstream only after a confirmed 2xx debit.
- Confirmed insufficient-funds rejections retain the existing structured 402 body.
- Non-402 4xx, 5xx, connection failures, timeouts, unexpected debit exceptions, unknown outcomes, and missing debit identity for billable prediction routes return a client-safe 503.
- The 503 response includes `Retry-After: 1` and a bounded or generated `X-Request-ID`.
- Contribution ingestion and MLflow registry bypasses are unchanged.
- Debit outcome logs carry normalized outcome, opaque key ID, model ID, idempotency key, request ID, endpoint, attempt count, and upstream status when available.

## Passing Validation

```text
pytest tests/unit/test_middleware tests/unit/test_model_serving_auth.py --no-cov -q
119 passed
```

This includes route-level Model 30 assertions for debit 409, debit 500, connection failure, and timeout. Every failure case asserts that `serving_service.serve_prediction` was not awaited.

```text
pytest tests/integration/test_model_30_mlflow_serving.py --no-cov -q
7 passed, 1 skipped
```

```text
pytest tests/unit/test_contributions_endpoint.py --no-cov -q
19 passed
```

```text
ruff check src/middleware/auth.py \
  tests/unit/test_middleware/test_auth_middleware.py \
  tests/unit/test_middleware/test_auth_middleware_billing.py \
  tests/unit/test_middleware/test_auth_middleware_stopiteration.py \
  tests/unit/test_model_serving_auth.py
```

Ruff passed. Python compilation, JSON parsing, and `git diff --check` also passed.

## Broader Suite Limitation

The first full-unit attempt could not collect because DSPy tried to create a SQLite cache in a read-only home location. Redirecting `DSPY_CACHEDIR` to `/private/tmp/hok-2758-dspy-cache` allowed collection of 3,144 tests, but the legacy full suite then reported pre-existing API endpoint expectation failures and timed out during an external MLflow registry health retry. An isolated first failure expected dependency-rich health output while the current endpoint returned `dependency_checks: skipped`; it was unrelated to the auth debit changes.

The focused middleware, Model 30 route, Model 30 integration, and contribution suites all pass and cover the HOK-2758 acceptance criteria.

## Operational Follow-up

- Deploy the API containment.
- Query debit failures by request ID and confirm they correlate to API 503 responses without Model 30 inference records.
- Reconcile accepted debit counts against served billable predictions.
- Confirm contribution requests continue to generate no debit attempts.
