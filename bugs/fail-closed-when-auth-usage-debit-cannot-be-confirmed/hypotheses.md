# HOK-2758 Root-Cause Hypotheses

## Hypothesis 1: Dispatch intentionally ignores the generic debit error outcome

**Proposed Root Cause:**

`APIKeyAuthMiddleware.dispatch()` returns 402 only for `debit_outcome == "rejected"`. The `"error"` outcome falls through to `call_next(request)`.

**Why This Could Cause Observed Behavior:**

Both debit 5xx responses and transport failures become `"error"` in `_debit_usage()`. Because no dispatch branch blocks that value, the Model 30 route executes and serves a prediction without a confirmed debit.

**How to Test:**

Mock a valid auth result and `_debit_usage(return_value="error")`, call `dispatch()` with an `AsyncMock` downstream handler, and inspect whether it is awaited.

**Expected Outcome if Correct:**

The current code awaits the downstream handler and returns its response. After the fix it returns 503 and the handler is not awaited.

**Priority:** High

**Likelihood:** High
**Status:** Confirmed

## Hypothesis 2: The dispatch exception guard independently preserves fail-open behavior

**Proposed Root Cause:**

The broad exception handler around `_debit_usage()` converts unexpected exceptions to `"error"` and explicitly logs that it is allowing the request.

**Why This Could Cause Observed Behavior:**

Failures that escape `_debit_usage()`, including the historical coroutine `StopIteration` boundary case, take the same unhandled outcome path and invoke inference.

**How to Test:**

Make `_debit_usage()` raise `RuntimeError("coroutine raised StopIteration")` and spy on `call_next()`.

**Expected Outcome if Correct:**

The existing test shows the handler is called. The corrected contract should return a controlled retryable 503 rather than a generic 500 or a served prediction.

**Priority:** High

**Likelihood:** High
**Status:** Confirmed

## Hypothesis 3: A missing key ID permits a billable request with no debit attempt

**Proposed Root Cause:**

Debit execution is guarded by `if validation_result.key_id`; a valid validation response without `key_id` skips the entire debit block.

**Why This Could Cause Observed Behavior:**

The acceptance criterion says an unconfirmed debit must never serve a billable prediction. A missing identifier makes the debit impossible but currently allows `call_next()`.

**How to Test:**

Return `ValidationResult(is_valid=True, key_id=None, ...)` for a Model 30 prediction and spy on both `_debit_usage()` and the downstream handler.

**Expected Outcome if Correct:**

Current code skips debit and calls the handler. Corrected code returns a client-safe 503 for the billable route without attempting inference.

**Priority:** Medium

**Likelihood:** Medium
**Status:** Confirmed by code inspection

## Hypothesis 4: Insufficient correlation fields hide the revenue-integrity failure mode

**Proposed Root Cause:**

Debit logs use different shapes by outcome. HTTP failures omit request ID and normalized outcome, transport failures are plain text, 402 omits key ID and idempotency key, and 2xx results are not logged.

**Why This Could Cause Observed Behavior:**

Operators cannot reliably join debit attempts to API responses or prove that only confirmed debits reach inference, increasing detection and incident-analysis time.

**How to Test:**

Capture logs for 2xx, 402, 404/409, 500, timeout, and connection failure and assert a common non-secret field set.

**Expected Outcome if Correct:**

Current records are incomplete and inconsistent. Corrected records include outcome, opaque key ID, model ID, idempotency key, and request ID for every debit result.

**Priority:** Medium

**Likelihood:** High
**Status:** Confirmed
