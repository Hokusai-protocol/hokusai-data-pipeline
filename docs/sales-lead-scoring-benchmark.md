# Sales Lead Scoring Benchmark

## Overview

This benchmark defines the launch-time evaluation contract for Hokusai's sales
lead scoring model. The model is evaluated on observed prospect conversations
and passes DeltaOne when its qualified meeting rate reaches the launch threshold
on a provenance-controlled benchmark dataset.

## Primary Metric

- Metric name: `sales:qualified_meeting_rate`
- Scorer ref: `sales:qualified_meeting_rate`
- Direction: `higher_is_better`
- Unit of analysis: `prospect_conversation`

The scorer is already registered in the built-in scorer registry and computes
the fraction of observed prospect conversations that result in a qualified
meeting.

## Metric Family

The benchmark uses the `proportion` metric family. DeltaOne comparisons and
basis-point conversion therefore operate on a score in the closed interval
`[0.0, 1.0]`.

## DeltaOne Threshold

The DeltaOne launch threshold is `0.15`, meaning the candidate model must reach
at least a 15% qualified meeting rate on the benchmark dataset.

Worked threshold conversion:

```text
0.15 x 10000 = 1500 bps
```

## Basis-Point Conversion

For `proportion` metrics, convert the metric value to basis points with:

```text
bps = rate x 10000
```

Use `ROUND_HALF_EVEN` when conversion requires rounding. Example:

```text
0.20 -> 2000 bps
```

## Dataset Inputs and Provenance

The benchmark dataset consists of `sales_outcome_row/v1` records with:

- `unit_of_analysis = "prospect_conversation"`
- `measurement_policy = "online_ab"`
- `metric_name = "sales:qualified_meeting_rate"`
- `scorer_ref = "sales:qualified_meeting_rate"`

Required provenance expectations:

- Each row must carry stable `benchmark_spec_id`, `eval_id`, `model_id`,
  `campaign_id`, and `unit_id` values.
- `prospect_id`, `conversation_id`, `arm`, `observed_at`,
  `label_observed_at`, and `label_available_at` must trace the row back to the
  underlying CRM and experiment assignment records.
- `source_system` must identify the system of record used to derive the label.
- `coverage_fraction` must be `1.0` for fully observed launch examples.
- Dataset production must preserve the original online A/B assignment and
  outcome window used for label collection.

## Contributor Attribution

Contributor attribution for this benchmark is keyed by `model_id`. The
`sales_outcome_row/v1` schema does not include row-level contributor or wallet
fields, so all rows in a single evaluation are attributed to the model owner
identified by the benchmark spec and MLflow run metadata.

## Wallet Weight Rules

Wallet allocation is defined at the benchmark-spec level, not in individual
dataset rows.

- A single-contributor launch evaluation uses one wallet with `weight_bps = 10000`.
- If multiple wallets are ever supplied, weights must sum to exactly `10000`
  basis points.
- When a single model owner is responsible for the whole evaluation, that owner
  receives the full allocation.

## Guardrails

The benchmark reuses the standard sales mint-blocking guardrails:

- `sales:unsubscribe_rate <= 0.03`
- `sales:spam_complaint_rate <= 0.005`

Both guardrails are blocking.

## Worked Example

The example spec fixture is
[`schema/examples/sales_eval_spec.lead_scoring.v1.json`](../schema/examples/sales_eval_spec.lead_scoring.v1.json).

The benchmark rows are:

- [`schema/examples/sales_outcome_row.lead_scoring_qualified.v1.json`](../schema/examples/sales_outcome_row.lead_scoring_qualified.v1.json)
- [`schema/examples/sales_outcome_row.lead_scoring_unqualified.v1.json`](../schema/examples/sales_outcome_row.lead_scoring_unqualified.v1.json)

Three qualified rows yield:

```text
qualified_meeting_rate = 3 / 3 = 1.0 = 10000 bps
```

One qualified row plus two unqualified rows yields:

```text
qualified_meeting_rate = 1 / 3 = 0.3333... = 3333 bps after ROUND_HALF_EVEN
```

The integration test
[`tests/integration/test_sales_lead_scoring_benchmark.py`](../tests/integration/test_sales_lead_scoring_benchmark.py)
uses these examples to verify a valid `DeltaOneAcceptanceEvent` and
`MintRequest` for the accepted case.

## Related Documents

- [`docs/sales-custom-outcome-eval-contract.md`](./sales-custom-outcome-eval-contract.md)
- [`docs/sales-custom-evals-mint-eligibility.md`](./sales-custom-evals-mint-eligibility.md)
- [`docs/deltaone-acceptance-event.md`](./deltaone-acceptance-event.md)
- [`docs/mint-request.md`](./mint-request.md)
