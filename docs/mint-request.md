# MintRequest Queue (HOK-1276)

## Overview

When a DeltaOne evaluation is accepted, the pipeline publishes a durable `MintRequest` message to Redis as the primary handoff before advancing the canonical baseline score in MLflow. The legacy token mint hook still runs, but only as a secondary audit or dry-run side effect after Redis publication succeeds. See `docs/mint-rail.md` for the full mint topology, operator runbook, and scheduler enablement gate.

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
| `attestation_hash` | `0x`-prefixed 64-hex | SHA-256 of the canonical attestation payload |
| `idempotency_key` | `0x`-prefixed 64-hex | Canonical dedup key (see below) |
| `baseline` | `0x`-prefixed 64-hex (optional) | Latest on-chain block hash used as the authorization baseline |
| `baselineCommitment` | `0x`-prefixed 64-hex | Required. Authoritative on-chain baseline weight head |
| `candidateCommitment` | `0x`-prefixed 64-hex | Required. SHA-256 Merkle root of candidate weights |
| `attesterSignature` | `0x`-prefixed 130-hex (optional) | Attester ECDSA signature over attestation payload |
| `signingDigest` | `0x`-prefixed 64-hex (optional) | EIP-712 digest signed by the hardware-wallet attester |
| `totalSamples` | integer `>= 1` | Required top-level sample count for DeltaVerifier ABI |
| `evaluation` | object | Scores, costs, statistical metadata |
| `contributors` | array | Wallet addresses + `weight_bps` with optional submission traceability fields |

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
idempotency_key = 0x + sha256("{model_id_uint}:{bare_attestation_hash}")
```

Computed by `make_idempotency_key()` in `src/evaluation/event_payload.py`. The bare hash is the 64-hex SHA-256 without the `0x` prefix. The resulting key is `0x`-prefixed lowercase 64-hex.

`eval_id` remains required on the payload as pipeline run metadata and is forwarded downstream as `pipelineRunId`, but it is not part of mint replay identity.

Recovery invariant: if the pipeline crashes after detecting an accepted evaluation but before the mint request is durably published, re-running the same evaluation over unchanged content republishes the same `idempotency_key`. A genuine content change produces a new key because `attestation_hash` changes.

Cutover note: this is a pre-mainnet breaking change from the older 3-component key format `sha256("{model_id_uint}:{eval_id}:{bare_attestation_hash}")`. Any queued or fixture payloads using the old formula must be regenerated before enabling the new producer.

Do **not** reimplement this formula — use the HOK-1266 helper.

## Attestation Hash Formula

`attestation_hash` is not the HEM content hash. It is the SHA-256 of the canonical JSON payload produced by `src/cli/attestation.py`, with keys sorted and compact separators.

For DeltaOne minting, that payload includes:

- `model_id`
- `eval_spec` (`"deltaone"`)
- `provider`
- `seed`
- `temperature`
- `results` (the serialized DeltaOne decision)
- `benchmark_spec_id` when available
- `dataset_hash` when available
- `attribution_report_hash` when attribution has run

`attribution_report_hash` is itself the SHA-256 of the full canonical attribution report. This keeps the mint attestation sensitive to deterministic attribution changes without making the attestation hash equal to the HEM hash.

## Publish ordering

The sequence within `DeltaOneMintOrchestrator._execute_mint()` for accepted evaluations is:

1. Build `DeltaOneAcceptanceEvent`
2. Build and validate `MintRequest`
3. Dispatch `deltaone.achieved` webhook
4. **`mint_request_publisher.publish(mint_request)`**
5. Notify auth-service with `pending` reward entitlements
6. `_advance_canonical_score()` in MLflow
7. Call `mint_hook.mint()` as a secondary audit or dry-run action
8. Notify auth-service with `claimable` reward entitlements when vesting details are available

If `publish()` raises a `RedisError`, the exception propagates and steps 5-6 are never reached. This preserves the recovery invariant: a crash between detection and publish means the next evaluation re-detects the improvement and re-publishes the same key for unchanged content.

If the producer cannot derive a positive integer candidate sample size from the accepted DeltaOne decision, MintRequest construction fails closed before Redis publish. In that case, canonical score advancement and the legacy mint hook are both skipped.

Auth-service notification failures are logged but do not roll back the already durable Redis handoff or the canonical advancement. Legacy hook failures, skips, and dry-runs are also non-blocking and are recorded separately in MLflow tags such as `hokusai.mint.legacy_status`.

## Signing Flow

When the mint authorization env block is configured, the producer builds the exact EIP-712 typed data from the draft `MintRequest`, derives the digest that the contract verifies, and logs a human-readable rendering of that exact typed data for the attester operator. The typed data includes:

- `modelIdUint`
- `baselineCommitment`
- `candidateCommitment`
- `baseline` (latest on-chain block hash)
- `attestationHash`
- `totalSamples`

The intended operator sequence is:

1. Producer resolves `baseline` from `ETH_RPC_URL`
2. Producer builds and renders the exact typed data
3. Hardware-wallet attester signs that typed data out-of-band
4. Signature is injected through `ATTESTER_SIGNATURE`
5. Producer verifies the signature against `MINT_ATTESTER_ADDRESS`
6. Producer publishes `baseline`, commitments, `signingDigest`, and `attesterSignature` on the `MintRequest`

If `MINT_REQUIRE_ONCHAIN_BASELINE` is set to anything other than `false`, `ETH_RPC_URL` becomes mandatory and a baseline-read failure aborts publish before canonical advancement.

`baselineCommitment` is resolved from `DeltaVerifier.modelWeightHead(modelId)` and falls back to `ModelRegistry.weightGenesis(modelId)` only when the on-chain head is zero. The producer may recompute the local baseline artifact commitment for drift detection, but it never substitutes the local hash for the chain-derived value. Missing or malformed weight commitments now fail the MintRequest build before Redis publish or canonical score advancement.

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

Contributors are derived automatically from the attribution report for the exact candidate run whenever the MLflow tag `hokusai.attribution_report_artifact_uri` is present. The orchestrator loads the report artifact, filters out zero/negative-lift contributors, validates wallets as `0x`-prefixed Ethereum addresses, and re-apportions `weight_bps` from positive `raw_score` so the published weights sum to exactly `10000`.

Fallback order is:

- attribution report from `hokusai.attribution_report_artifact_uri`
- benchmark spec contributors (`spec["contributors"]`)
- MLflow run tag `hokusai.contributors` (JSON array)

Fallback keeps older callers working when no attribution report is available. If a report is present but invalid, mint publication aborts before canonical score advancement.

For fallback spec/tag contributors, each entry needs:

- `wallet_address`: `0x`-prefixed Ethereum address (40 hex digits)
- `weight_bps` (int, 0–10000) or `weight` (float, 0–1.0)

The published `weight_bps` values **must sum to exactly 10000**. If no valid contributors are found, the publisher raises `EventPayloadError` and the mint path aborts before canonical score advancement.

Optional contributor traceability fields are preserved on each contributor row:

- `submissionId`: contributor submission identifier used by the data contribution pipeline
- `contributionBatchId`: optional batch/job reference when one submission maps to a broader batch
- `contributorId`: optional contributor identity distinct from the wallet address

The producer sorts contributors deterministically by wallet and traceability metadata before building the acceptance event and MintRequest payload. This keeps serialized payloads stable across replays without changing the idempotency key formula.

## Auth-service reward entitlements

After a successful MintRequest publish, the pipeline posts a `reward_entitlement.v1` payload to auth-service using the existing internal auth-service notifier configuration:

- `pending` is emitted immediately after Redis publish and includes contributor `weight_bps`, `submissionId`, and `contributionBatchId`
- `claimable` is emitted after the secondary mint hook only when vesting or claimable details are returned

Both notifications use an idempotency key derived from the MintRequest key and status:

```text
{mint_request.idempotency_key}:reward_entitlement:{status}
```

## Privacy

Wallet addresses are **not** logged at INFO level. They appear only in DEBUG-level traces if needed.

## No retries / DLQ

The `MintRequestPublisher` does not implement retries or a dead-letter queue. The downstream consumer is responsible for idempotent processing, retry logic, and DLQ handling.

## Related

- `docs/mint-rail.md` — canonical mint topology, monitoring, and runbook
- `docs/deltaone-acceptance-event.md` — the acceptance event published before the mint
- `src/events/publishers/mint_request_publisher.py` — publisher implementation
- `src/events/schemas.py` — `MintRequest`, `MintRequestEvaluation`, `MintRequestContributor`
- `src/evaluation/event_payload.py` — HOK-1266 conversion helpers (`to_basis_points`, `to_micro_usdc`, `make_idempotency_key`)
