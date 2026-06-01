# HOK-1943 Investigation

## CloudWatch Findings

24-hour review for `/ecs/hokusai-api-development` ending 2026-05-31 found 10 `validation_422` events on `POST /api/v1/models/30/predict`.

| Timestamp (UTC) | Source IPs | Count | Preceding event |
| --- | --- | --- | --- |
| 2026-05-30 17:12:36 | `10.0.103.145` | 1 | Three `503` responses during cold load |
| 2026-05-30 17:27:24 | `10.0.103.145`, `10.0.102.142`, `10.0.101.180` | 4 | MLflow artifact download and cold load |
| 2026-05-30 17:43:43 | `10.0.103.145`, `10.0.101.180`, `10.0.102.142` | 4 | Warm cache |
| 2026-05-30 18:06:07 | `10.0.103.145` | 1 | Second MLflow artifact download / cold load |

## Pattern Summary

- All callers were private `10.0.x.x` ECS addresses, so this traffic was internal rather than public internet traffic.
- The 4-request bursts hit all three ECS instances at once, which matches a parallel orchestration caller rather than manual experimentation.
- Every sampled 422 was preceded by `Prediction request for model 30` and `model_30_latency_trace` with `outcome=validation_error`.
- Current logs did not include caller identity, request ID correlation, or field-level validation details for this path.

## Root Cause Classification

`caller_payload_bug`

Existing test coverage already captured the failing request shape: a flat benchmark-row payload under `inputs`, for example `schema_version`, `task_descriptor`, `allowed_models`, and `max_cost_usd`, instead of the nested serving contract with `inputs.task.description` and `inputs.task.task_type`.

That rejected shape matches the benchmark/evaluation row contract, not the live model-serving contract. The parallel, internal-only request pattern is consistent with Strategy Explorer or a related Wavemill orchestration path reusing benchmark-row payloads against the serving endpoint.

## Attribution Limits Before This Change

- No `user_id` or `api_key_id` was logged on the inner model-30 validation path.
- No safe caller fingerprint or request ID was emitted specifically for 422 validation failures.
- Payload field names could be inferred from the Pydantic error, but the originating caller could not be named from production logs alone.
