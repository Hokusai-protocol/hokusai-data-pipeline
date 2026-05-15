# MintRequest Queue (HOK-1276)

## Overview

When a DeltaOne evaluation is accepted, the pipeline publishes a durable `MintRequest` message to Redis as the primary handoff before advancing the canonical baseline score in MLflow. The legacy token mint hook still runs, but only as a secondary audit or dry-run side effect after Redis publication succeeds.

The Redis payload authorizes a mint, but it is not the final mint result. When the downstream mint
service enables vesting, the final reward may be split into immediate liquid and vested portions.
That post-mint split is reported only after the secondary HTTP mint hook returns.

## Queue

- **Queue name**: `hokusai:mint_requests`
- **Redis instance**: same as `hokusai:model_ready_queue`
- **Publish operation**: `LPUSH` (consumers `RPOP` for FIFO ordering)

## Schema

- **Pydantic model**: `MintRequest` in `src/events/schemas.py`
- **JSON Schema**: `schema/mint_request.v1.json`
- **Example**: `schema/examples/mint_request.v1.json`

### Key fields

| Field | Type | Notes |
|---|---|---|
| `message_type` | `"mint_request"` | Fixed literal |
| `schema_version` | `"1.0"` | Schema version |
| `message_id` | UUID string | Per-message unique ID |
| `timestamp` | ISO-8601 UTC | Publish time |
| `model_id` | string | Human-readable model identifier |
| `model_id_uint` | decimal string | uint256 model ID for on-chain use |
| `eval_id` | string | Evaluation run identifier |
| `attestation_hash` | `0x`-prefixed 64-hex | SHA-256 of HEM payload |
| `idempotency_key` | `0x`-prefixed 64-hex | Canonical dedup key (see below) |
| `totalSamples` | integer `>= 1` | Required top-level sample count for DeltaVerifier ABI |
| `evaluation` | object | Scores, costs, statistical metadata |
| `contributors` | array | Wallet addresses + `weight_bps` (must sum to 10000) |

### Evaluation sub-object

All score fields are in **basis points** (0–10000). Cost fields are in **USDC micro-units** (6 decimals, e.g. `5000000` = $5.00).

| Field | Notes |
|---|---|
| `baseline_score_bps` | Baseline score in bps |
| `new_score_bps` | Candidate (new) score in bps |
| `max_cost_usd_micro` | Budget ceiling from eval spec |
| `actual_cost_usd_micro` | Actual evaluation cost |
| `sample_size_baseline` | Optional — sample count |
| `sample_size_candidate` | Optional — sample count |
| `ci_low_bps` / `ci_high_bps` | Optional — 95% CI in bps |
| `p_value` | Optional |
| `statistical_method` | Optional |

`totalSamples` is camelCase to match the downstream DeltaVerifier ABI. The producer derives it from the accepted DeltaOne decision with the rule `totalSamples = evaluation.sample_size_candidate = decision.n_current`.

## Idempotency Key

```
idempotency_key = 0x + sha256("{model_id_uint}:{eval_id}:{bare_attestation_hash}")
```

Computed by `make_idempotency_key()` in `src/evaluation/event_payload.py`. The bare hash is the 64-hex SHA-256 without the `0x` prefix. The resulting key is `0x`-prefixed lowercase 64-hex.

Do **not** reimplement this formula — use the HOK-1266 helper.

## Publish ordering

The sequence within `DeltaOneMintOrchestrator._execute_mint()` for accepted evaluations is:

1. Build `DeltaOneAcceptanceEvent`
2. Build and validate `MintRequest`
3. Dispatch `deltaone.achieved` webhook
4. **`mint_request_publisher.publish(mint_request)`**
5. `_advance_canonical_score()` in MLflow
6. Call `mint_hook.mint()` as a secondary audit or dry-run action

If `publish()` raises a `RedisError`, the exception propagates and steps 5-6 are never reached. This preserves the recovery invariant: a crash between detection and publish means the next evaluation re-detects the improvement and re-publishes.

If the producer cannot derive a positive integer candidate sample size from the accepted DeltaOne decision, MintRequest construction fails closed before Redis publish. In that case, canonical score advancement and the legacy mint hook are both skipped.

Legacy hook failures, skips, and dry-runs do not roll back the already durable Redis handoff or the canonical advancement. They are recorded separately in MLflow tags such as `hokusai.mint.legacy_status`.

## Post-mint vesting semantics

A successful `MintRequest` publish or `deltaone.achieved` webhook does **not** imply that 100% of
the reward is immediately liquid. If the downstream mint endpoint returns vesting details, the
pipeline preserves them in post-mint surfaces:

- MLflow tags under `hokusai.mint.vesting.*`
- Consumed-attestation audit metadata as `mint_vesting`
- `deltaone.minted` webhook payloads as an optional `vesting` object

Supported `vesting` fields are additive and optional:

- `liquid_amount`
- `vested_amount`
- `vault_address`
- `schedule_id`
- `claimable_amount`
- `vesting_config`

Legacy mint endpoints that return only `status`, `audit_ref`, `timestamp`, and `error` remain
fully supported. In that case, no `vesting` block is emitted.

## Contributor data

Contributors must come from the benchmark spec (`spec["contributors"]`) or from the MLflow run tag `hokusai.contributors` (JSON array). Each entry needs:

- `wallet_address`: `0x`-prefixed Ethereum address (40 hex digits)
- `weight_bps` (int, 0–10000) or `weight` (float, 0–1.0)

The `weight_bps` values **must sum to exactly 10000**. If no valid contributors are found, the publisher raises `EventPayloadError` and the mint path aborts before canonical score advancement.

## Privacy

Wallet addresses are **not** logged at INFO level. They appear only in DEBUG-level traces if needed.

## No retries / DLQ

The `MintRequestPublisher` does not implement retries or a dead-letter queue. The downstream consumer is responsible for idempotent processing, retry logic, and DLQ handling.

## Related

- `docs/deltaone-acceptance-event.md` — the acceptance event published before the mint
- `src/events/publishers/mint_request_publisher.py` — publisher implementation
- `src/events/schemas.py` — `MintRequest`, `MintRequestEvaluation`, `MintRequestContributor`
- `src/evaluation/event_payload.py` — HOK-1266 conversion helpers (`to_basis_points`, `to_micro_usdc`, `make_idempotency_key`)
