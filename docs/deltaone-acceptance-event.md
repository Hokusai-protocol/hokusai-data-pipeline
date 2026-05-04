# DeltaOne Acceptance Event Contract

**Schema version:** `deltaone.acceptance/v1`
**Module:** `src/evaluation/event_payload.py`
**Schema file:** `schema/deltaone_acceptance_event.v1.json`
**Example fixture:** `schema/examples/deltaone_acceptance_event.v1.json`

## Overview

The `DeltaOneAcceptanceEvent` is a versioned, deterministic event emitted by
`DeltaOneMintOrchestrator` after a candidate MLflow run passes primary evaluation and guardrail
gating. It captures all information required for the on-chain `DeltaVerifier` to validate and
authorize a token mint, and is the canonical handoff point for the Redis publisher (HOK-1276).

All numeric quantities are normalized for unambiguous on-chain consumption:

- **Scores and deltas:** basis points (integer 0–10000), `ROUND_HALF_EVEN`
- **Costs:** USDC micro-units (integer, 6 decimals), `ROUND_HALF_EVEN`
- **Hashes:** lowercase 0x-prefixed 64-hex SHA-256

## Field Reference

| Field | Type | Description |
|---|---|---|
| `event_version` | `"deltaone.acceptance/v1"` | Version literal; changes on breaking schema changes |
| `model_id` | `str` | Canonical Hokusai model identifier |
| `model_id_uint` | `str` (decimal) | `model_id` as uint256 decimal string for on-chain consumption |
| `eval_id` | `str` | Evaluation identifier from `hokusai.eval_id` run tag |
| `mlflow_run_id` | `str` | Candidate MLflow run ID |
| `benchmark_spec_id` | `str` | Benchmark spec that governed this evaluation |
| `primary_metric_name` | `str` | Canonical Hokusai metric name (e.g. `accuracy`) |
| `primary_metric_mlflow_name` | `str` | Colon-normalized MLflow key (e.g. `custom_accuracy`) |
| `metric_family` | `str` | Comparator family: `proportion`, `continuous`, `zero_inflated_continuous`, `rank_or_ordinal` |
| `baseline_score_bps` | `int` [0, 10000] | Baseline model score in basis points |
| `candidate_score_bps` | `int` [0, 10000] | Candidate model score in basis points |
| `delta_bps` | `int` [0, 10000] | `candidate_score_bps - baseline_score_bps`; always non-negative for accepted events |
| `delta_threshold_bps` | `int` [0, 10000] | Minimum delta threshold in basis points |
| `attestation_hash` | `str` (0x-SHA256) | SHA-256 of canonical HEM payload; proof of evaluation inputs |
| `idempotency_key` | `str` (0x-SHA256) | Replay-safe key; see formula below |
| `guardrail_summary` | object | Guardrail evaluation aggregate; see nested schema |
| `max_cost_usd_micro` | `int` ≥ 0 | Cost cap from measurement policy in USDC micro-units |
| `actual_cost_usd_micro` | `int` ≥ 0 | Actual eval cost from run tags in USDC micro-units |

### Guardrail Summary Fields

| Field | Type | Description |
|---|---|---|
| `total_guardrails` | `int` ≥ 0 | Count of blocking guardrails evaluated |
| `guardrails_passed` | `int` ≥ 0 | Count of blocking guardrails that passed |
| `breaches` | array | List of `DeltaOneGuardrailBreach` objects (empty on full pass) |

### Guardrail Breach Fields

| Field | Type | Description |
|---|---|---|
| `metric_name` | `str` | Guardrail metric name |
| `observed_bps` | `int` | Observed value in basis points |
| `threshold_bps` | `int` | Threshold in basis points |
| `observed` | `float` | Raw observed value |
| `threshold` | `float` | Raw threshold value |
| `direction` | `str` | `higher_is_better` or `lower_is_better` |
| `policy` | `str` | Enforcement policy (e.g. `reject_mint`) |
| `reason` | `str` | Human-readable breach description |

## Basis Points Mapping by Metric Family

All score fields are reported in basis points (integer 0–10000).

| `metric_family` | Mapping Rule |
|---|---|
| `proportion` | `value × 10000`, `ROUND_HALF_EVEN`. Input **must** be in `[0, 1]`; values outside this range are rejected. |
| `continuous` | `min(value, 1.0) × 10000`, `ROUND_HALF_EVEN`. Values > 1.0 are clamped to 10000 bps (v1 limitation; callers should pre-normalize). |
| `zero_inflated_continuous` | Same as `continuous`. |
| `rank_or_ordinal` | Same as `continuous`. |

**v1 limitation:** For non-proportion families, per-observation data is unavailable in aggregate
HEM records. Callers must provide values already normalized to `[0, 1]` (e.g. NDCG@k, rank
correlation coefficients). Values > 1.0 are clamped to 10000 bps and logged as a warning.

## Rounding and Overflow Rules

- Rounding mode: `ROUND_HALF_EVEN` (banker's rounding) throughout — never Python `round()`.
- NaN and infinity are rejected for all numeric fields.
- Negative values are rejected for all score, cost, and delta fields.
- Proportion values outside `[0, 1]` are rejected.
- Non-proportion values outside `[0, 1]` are **clamped** (not rejected) to preserve v1 backward
  compatibility for callers that provide unnormalized scores.

## Attestation Hash

`attestation_hash` is the SHA-256 of the canonicalized HEM (Hokusai Evaluation Manifest) payload:

```python
canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
attestation_hash = "0x" + sha256(canonical.encode("utf-8")).hexdigest()
```

Downstream consumers can verify the attestation by reproducing the same canonical JSON from the
HEM payload stored in MLflow artifacts.

> **Divergence from HOK-1269:** The v1 acceptance event uses `ROUND_HALF_EVEN` throughout.
> The older HOK-1269 design note specified half-up rounding. Follow HOK-1266 for this event.

## Idempotency Key Formula

```python
bare_hash = attestation_hash[2:]  # strip 0x prefix
raw = f"{model_id_uint}:{eval_id}:{bare_hash}"
idempotency_key = "0x" + sha256(raw.encode("utf-8")).hexdigest()
```

The key is deterministic given the same `(model_id_uint, eval_id, attestation_hash)` triple.
It is stored in `hokusai.mint.idempotency_key` on the MLflow run and passed to `TokenMintHook`.

## Versioning Policy

- Field additions are backward-compatible; bump only when breaking field renames or type changes occur.
- The `event_version` literal changes from `"deltaone.acceptance/v1"` to `"deltaone.acceptance/v2"` on the next breaking change.
- `hokusai-token` should pin `schema/examples/deltaone_acceptance_event.v1.json` in its contract tests so any schema drift fails CI on both sides.

## Downstream Validation

### With Pydantic (Python)

```python
from src.evaluation.event_payload import DeltaOneAcceptanceEvent

event = DeltaOneAcceptanceEvent(**event_dict)  # raises ValidationError on schema violation
```

### With JSON Schema

```python
import json, jsonschema

schema = json.loads(open("schema/deltaone_acceptance_event.v1.json").read())
instance = json.loads(open("schema/examples/deltaone_acceptance_event.v1.json").read())
jsonschema.validate(instance, schema)  # raises ValidationError on violation
```

### Schema Drift Detection

The test `tests/unit/test_event_payload.py::TestJsonSchemaDrift::test_schema_file_matches_generated`
regenerates the schema from the Pydantic model and compares it byte-for-byte to the committed
`schema/deltaone_acceptance_event.v1.json`. Any model change that alters the JSON Schema will
fail CI immediately.

## Relationship to HOK-1276 (Redis Publisher)

`DeltaOneMintOrchestrator` exposes the constructed event via:

1. `MintOutcome.acceptance_event` — the fully validated `DeltaOneAcceptanceEvent` object.
2. `mint_hook.mint(..., metadata={"deltaone_acceptance_event": event.model_dump()})` — the
   serialized event dict passed into mint metadata for downstream handoff.

HOK-1276 (MintRequest Redis publisher) should read `deltaone_acceptance_event` from mint metadata
and map the relevant fields onto the `MintRequest` struct. It **may** omit or recompute
`delta_bps` for the current on-chain struct, but should not redefine bps/idempotency semantics.

The on-chain `DeltaVerifier` may recompute reward delta from `baseline_score_bps` and
`candidate_score_bps` directly. `delta_bps` is included in the acceptance event for auditability
but may not be forwarded to the current contract struct.
