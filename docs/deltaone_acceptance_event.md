# DeltaOne Acceptance Event Contract

This page documents the canonical event the
`DeltaOneMintOrchestrator` publishes when a candidate run is accepted for
minting.  Downstream consumers — the Redis MintRequest publisher (HOK-1276)
and the on-chain `DeltaVerifier` in `hokusai-token` — should validate every
incoming payload against this schema before acting on it.

## Versioning

- Event version: `deltaone.acceptance/v1`
- Pydantic model: `src/evaluation/event_payload.DeltaOneAcceptanceEvent`
- JSON Schema artifact: [`docs/schemas/deltaone_acceptance_event_v1.schema.json`](schemas/deltaone_acceptance_event_v1.schema.json)
- Contract mapping fixture: [`tests/fixtures/deltaone_acceptance_event_v1_contract_mapping.json`](../tests/fixtures/deltaone_acceptance_event_v1_contract_mapping.json)

A breaking change to any field requires a new version (`deltaone.acceptance/v2`).
Additive, optional fields may ship under `v1` provided the JSON Schema is updated
and the Pydantic model retains `extra="forbid"` semantics.

## Field reference

| Field | Type | Units | Notes |
|-------|------|-------|-------|
| `event_version` | string literal | n/a | Always `deltaone.acceptance/v1` |
| `model_id` | string | n/a | Hokusai-internal model identifier |
| `model_id_uint` | string | uint256 (decimal) | Decimal-encoded `uint256` for ABI parity |
| `eval_id` | string | n/a | Stable evaluation id; used as `pipelineRunId` on chain |
| `mlflow_run_id` | string | n/a | Candidate MLflow run id for audit |
| `benchmark_spec_id` | string | n/a | BenchmarkSpec UUID/string |
| `primary_metric_name` | string | n/a | Canonical Hokusai name |
| `primary_metric_mlflow_name` | string | n/a | The colon-normalized MLflow key actually logged |
| `metric_family` | string | n/a | One of `proportion`, `continuous`, `zero_inflated_continuous`, `rank_or_ordinal` |
| `baseline_score_bps` | int | basis points (0..10000) | Baseline primary score |
| `candidate_score_bps` | int | basis points (0..10000) | Candidate primary score |
| `delta_bps` | int | basis points | `candidate_score_bps - baseline_score_bps` |
| `delta_threshold_bps` | int | basis points (0..10000) | Acceptance delta threshold |
| `attestation_hash` | string | 64-hex | SHA-256 over the canonical attestation payload |
| `idempotency_key` | string | 64-hex | `sha256("{model_id_uint}:{eval_id}:{attestation_hash}")` |
| `guardrails.total_guardrails` | int | n/a | Count configured in the spec |
| `guardrails.guardrails_passed` | int | n/a | `total_guardrails - len(breaches)` |
| `guardrails.breaches[]` | array | n/a | Audit-only; never zero-padded for chain |
| `max_cost_usd_micro` | int | USDC micro-units | `0` skips budget check (HOK-1269 convention) |
| `actual_cost_usd_micro` | int | USDC micro-units | `0` when no cost was logged |
| `evaluated_at` | string | ISO-8601 UTC | Mirrors `DeltaOneDecision.evaluated_at` |

## Deterministic conversion rules

All conversion in `src/evaluation/event_payload.py` flows through
`Decimal(str(value))` to avoid binary-float artifacts (e.g. `0.1 + 0.2 ==
0.30000000000000004`).

- **Basis points**:
  `bps = round_half_up(Decimal(str(value)) * 10000)` — applied to a normalized
  acceptance score in `[0, 1]`.  Inputs outside that band are rejected, not
  clamped.
- **USDC micro-units**:
  `micro = round_half_up(Decimal(str(value)) * 1_000_000)` — Decimal context
  is widened locally so values up to `uint256` survive multiplication.
- **Idempotency key**:
  `sha256("{model_id_uint}:{eval_id}:{attestation_hash}")`.  The model id is a
  decimal string (no leading zeros) and the attestation hash is 64 lowercase
  hex characters (any `sha256:` prefix is stripped).

## Non-proportion metric families

`to_basis_points` deliberately does **not** invent a default mapping for
arbitrary continuous, rank, or zero-inflated metrics.  For families other than
`proportion`, callers must already have normalized their score into `[0, 1]`
(e.g. via min/max scaling against a benchmark range) before producing the
event.  This keeps the on-chain consumer agnostic to family-specific semantics.

## Validating a received event

Downstream services should validate before acting:

```python
from jsonschema import Draft202012Validator
import json
from pathlib import Path

schema = json.loads(
    Path("docs/schemas/deltaone_acceptance_event_v1.schema.json").read_text()
)
Draft202012Validator(schema).validate(event_payload)
```

Or, if the consumer is in this repository:

```python
from src.evaluation.event_payload import DeltaOneAcceptanceEvent

event = DeltaOneAcceptanceEvent(**event_payload)  # raises ValidationError on drift
```

## Mapping to the on-chain `DeltaVerifier` struct

HOK-1269 §4.1 packs the single primary score into the `accuracy` slot of the
contract's `Metrics` struct; latency/sample slots are zero in the v1 contract.
The cost fields map straight through.  See
[`tests/fixtures/deltaone_acceptance_event_v1_contract_mapping.json`](../tests/fixtures/deltaone_acceptance_event_v1_contract_mapping.json)
for the full mapping table — that fixture is asserted in CI by
`tests/evaluation/test_event_contract_mapping.py`.

| Contract field | Event field |
|----------------|-------------|
| `pipelineRunId` | `eval_id` |
| `modelId` | `model_id_uint` |
| `baselineMetrics.accuracy` | `baseline_score_bps` |
| `newMetrics.accuracy` | `candidate_score_bps` |
| `maxCostUsd` | `max_cost_usd_micro` |
| `actualCostUsd` | `actual_cost_usd_micro` |
| `attestationHash` | `0x` + `attestation_hash` |
| `idempotencyKey` | `0x` + `idempotency_key` |

> Naming note: HOK-1269's MintRequest example uses `new_score_bps` and omits
> `delta_bps`.  This event keeps `candidate_score_bps`/`delta_bps` so the
> off-chain payload is self-describing for audit; the on-chain contract may
> recompute its own delta from the submitted scores.

## Operational guarantees

- The orchestrator refuses to emit a v1 event when `model_id_uint`,
  `eval_id`, or `benchmark_spec_id` is missing — better to fail loudly than
  publish an on-chain-incompatible event.
- The orchestrator passes the same `idempotency_key` to the `TokenMintHook`
  and persists it to MLflow as `hokusai.mint.idempotency_key`.  The
  attestation hash is stored separately under `hokusai.mint.attestation_hash`.
- Cost fields default to `0` when neither the spec nor the run carries a value.
  Per HOK-1269 §4.1, `0` means "skip budget check" on chain.
