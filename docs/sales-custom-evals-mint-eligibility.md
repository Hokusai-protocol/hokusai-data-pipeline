# Sales Custom Evals — Mint Eligibility

This document describes the five `eval_spec` policy patterns for sales outreach custom outcome
metrics, explains mint eligibility, and explains why historical revenue cannot score arbitrary
generated messages.

## Overview

Sales outreach models are evaluated on a primary metric of `revenue_per_1000_messages` — the
revenue attributed to sent messages, normalized to a per-1,000 basis. This metric is
zero-inflated: most messages produce no direct revenue; a small fraction produce a closed deal.

Because of this structure, the `metric_family` for all revenue-based sales specs is
`zero_inflated_continuous`, which routes DeltaOne comparator dispatch to the appropriate
statistical test.

DeltaOne can only mint a reward (transfer on-chain DeltaVerifier acceptance) when the
measurement policy provides a defensible causal or exact-correspondence path from generated
output to observed outcome. Five measurement policy patterns are recognized; four are mint
eligible.

## Measurement Policy Matrix

| Policy type | Mint eligible | How outcome is attributed |
|---|---|---|
| `online_ab` | Yes | Prospective randomized live treatment/control split collects outcomes for both arms |
| `reward_model` | Yes (with validated model) | A registered, validated reward model scores each message; model itself must be calibrated against held-out revenue outcomes |
| `off_policy` | Yes | Logged propensities from the production policy enable importance-weighted estimation over historical data |
| `exact_observed_output` | Yes | Generated output exactly matches a logged sent message via SHA-256 hash join; revenue is the historically observed outcome for that exact message |
| `diagnostic_only` | **No** | Logs diagnostic quality signals; no causal or exact-correspondence path to revenue exists |

All mint-eligible policies require `measurement_policy.mint_eligible: true` in the `eval_spec`
and are gated by DeltaOne before any on-chain acceptance event is emitted. The `diagnostic_only`
policy type sets `mint_eligible: false` and can never trigger a mint regardless of metric values.

## Why Historical Revenue Cannot Score Arbitrary Generated Messages

Historical revenue data records outcomes for messages that were actually sent. A newly generated
message — even if it resembles a past sent message — has no observed historical outcome unless it
exactly matches a logged sent message character-for-character.

Assigning revenue to an arbitrary generated text would require constructing a counterfactual:
"if we had sent this message instead, the prospect would have produced $X in revenue." Such
counterfactuals are not supported by historical data alone. Specifically:

- **Selection bias**: Messages that were sent were chosen by a policy. The prospect population
  that received any particular message type is not the same as the general prospect population.
  Applying historical revenue statistics from sent messages to new generated messages ignores
  this selection effect.

- **No outcome observation**: The prospect was never sent the generated message, so there is no
  observed response or revenue outcome to record.

- **Fuzzy attribution is unsupported**: Even if the generated message is semantically similar to
  a sent message, semantic similarity does not imply equal revenue outcome. Revenue depends on
  the full context of the sales interaction, not just message content.

The four mint-eligible policies each solve this problem differently:

- **`online_ab`** avoids counterfactuals entirely by collecting real outcomes prospectively from
  a randomized live split.
- **`reward_model`** uses a validated model that has been calibrated against real revenue
  outcomes to predict the expected revenue for a generated message.
- **`off_policy`** corrects for selection bias using logged propensities and importance
  weighting, enabling valid estimation from historical data when action support is sufficient.
- **`exact_observed_output`** bypasses the counterfactual problem by only attributing revenue
  when the generated output is byte-identical to a logged sent message that has an observed
  outcome record.

Diagnostic metrics (reply rate, quality score, tone score) can still be computed and logged for
any generated message. Logging diagnostics is useful for observability and model development but
is not sufficient to mint. A `diagnostic_only` spec captures this logging use case explicitly.

## Fixture Index

The following fixtures are located in `schema/examples/` and can be consumed by cross-repo E2E
tests (e.g., `gtm-backend` integration tests).

| Fixture file | Policy type | Mint eligible | Primary metric |
|---|---|---|---|
| `sales_eval_spec.online_ab.v1.json` | `online_ab` | Yes | `revenue_per_1000_messages` |
| `sales_eval_spec.reward_model.v1.json` | `reward_model` | Yes | `revenue_per_1000_messages` |
| `sales_eval_spec.off_policy.v1.json` | `off_policy` | Yes | `revenue_per_1000_messages` |
| `sales_eval_spec.exact_observed.v1.json` | `exact_observed_output` | Yes | `revenue_per_1000_messages` |
| `sales_eval_spec.diagnostic_only.v1.json` | `diagnostic_only` | No | `message_quality_score` |

All five fixtures validate against `EvalSpec.model_validate` from
`src/api/schemas/benchmark_spec.py`. Unit tests for these fixtures are in
`tests/unit/test_sales_eval_spec_fixtures.py`.

### Policy-Specific Notes

**`online_ab`** — Requires a live randomized split. `assignment_unit` is `prospect`. The
`outcome_window_days` field defines how long after message send to look for revenue events.
Both treatment and control arms must meet `min_treatment_size` / `min_control_size` before
the result is considered valid.

**`reward_model`** — Mint eligibility depends on the registered reward model being validated
and approved by the ML platform team. The `reward_model_hash` field pins the exact model
artifact. If the reward model is replaced or re-versioned, the `eval_spec` must be updated with
the new hash and re-approved. The `calibration_required: true` field enforces that the reward
model score has been calibrated against held-out real revenue outcomes.

**`off_policy`** — Requires that propensities (`logging_policy_scores`) were logged at inference
time for every prospect message. The `propensity_overlap_fraction` guardrail enforces minimum
action support before the importance-weighted estimate is trusted. `clipping_percentile: 99`
prevents extreme propensity weights from dominating the estimate.

**`exact_observed_output`** — The strictest policy. The `match_strategy: "sha256_hash"` field
means that only byte-identical matches (after canonicalization) are eligible. The
`fuzzy_match_rate` guardrail blocks the result if any fuzzy matches are detected. This policy
is appropriate when a sales model is re-scoring historical templates that were logged as sent.

**`diagnostic_only`** — No revenue attribution. All guardrails have `blocking: false`, meaning
they alert but do not block. The primary metric is `message_quality_score`, a heuristic score
that can be computed offline. Secondary metrics include reply rate, personalization score, and
tone appropriateness. This spec is appropriate for early-stage model development before a
mint-eligible measurement setup is in place.

## Implementation Order

When building a new sales outreach eval, follow this order:

1. **Start with `diagnostic_only`** to establish a logging baseline. Confirm that secondary
   metrics and guardrails are behaving as expected.

2. **Choose an eligible policy** based on available infrastructure:
   - If the sales platform supports A/B randomization → `online_ab`.
   - If a validated reward model exists → `reward_model`.
   - If propensities are logged in the serving path → `off_policy`.
   - If the model re-scores historical logged templates → `exact_observed_output`.

3. **Configure the `eval_spec`** by selecting the matching fixture and adjusting policy
   parameters (outcome window, coverage thresholds, model artifact reference) for your
   specific campaign or model.

4. **Register the `eval_spec`** by attaching it to the `BenchmarkSpec` row via
   `POST /api/v1/benchmark-specs` or `PATCH /api/v1/benchmark-specs/{spec_id}`. The `eval_spec`
   is stored as a JSONB column; see `docs/custom-outcome-evals-mlflow-foundation.md` for the
   storage contract.

5. **Run the evaluation** and confirm that the DeltaOne comparator dispatches correctly for
   `zero_inflated_continuous` (see `src/evaluation/comparators/zero_inflated.py`).

6. **Mint eligibility check** is performed automatically by the DeltaOne evaluation runner
   before any `MintRequest` is published to the Redis queue. A `diagnostic_only` spec will
   never produce a `MintRequest`.

## Website Benchmark Template Integration

The hokusai-site benchmark creation template should expose the five policy-backed fixtures when
building a sales custom eval:

- Display mint-eligible policies (`online_ab`, `reward_model`, `off_policy`,
  `exact_observed_output`) in a separate section from `diagnostic_only` logging.
- When a user selects a policy, pre-populate the `eval_spec` fields from the corresponding
  fixture in `schema/examples/`.
- Serialize the configured `eval_spec` into the `eval_spec` JSONB field described in
  `docs/custom-outcome-evals-mlflow-foundation.md` when submitting the benchmark spec.
- Show a clear "Not mint eligible" badge for `diagnostic_only` selections so users understand
  that secondary logging does not trigger on-chain rewards.
- `gtm-backend` E2E tests can reference the stable fixture paths
  `schema/examples/sales_eval_spec.*.v1.json` directly for contract testing without duplicating
  the fixture content.

## Related Docs

- [`docs/custom-outcome-evals-mlflow-foundation.md`](custom-outcome-evals-mlflow-foundation.md) —
  Storage contract for the `eval_spec` JSONB column on `benchmark_specs`.
- [`docs/mint-request.md`](mint-request.md) — DeltaOne `MintRequest` schema and on-chain
  acceptance event.
- [`docs/deltaone-acceptance-event.md`](deltaone-acceptance-event.md) — DeltaVerifier
  acceptance event payload and BPS encoding.
