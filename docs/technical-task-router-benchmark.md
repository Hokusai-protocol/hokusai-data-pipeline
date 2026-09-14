# Technical Task Router Benchmark (v2 canonical)

## Objective and Scope

This document defines the Hokusai benchmark contract for evaluating a technical task
router. Each sample contains a structured task descriptor, the models the router may use,
the workflow models it selected, and the per-sample budget and observed outcome.

> **Canonical metric (Model 30):** `technical_task_router.benchmark_score/v2` — a bounded
> composite — is the promotion and reward-gating metric. The v1
> `technical_task_router.success_under_budget/v1` score is retained only as a logged
> guardrail/diagnostic and is the first component of the composite. The v1 sections below
> describe the legacy row schema and diagnostics that remain in use as guardrails. See
> [v2 Composite Reward Benchmark](#v2-composite-reward-benchmark-canonical) and
> [Operator Rollback Notes](#operator-rollback-notes).

The legacy v1 benchmark score is:

```text
SuccessfulRunsWithinBudget / TotalRuns
```

## v2 Composite Reward Benchmark (canonical)

The canonical Model 30 reward metric is `technical_task_router.benchmark_score/v2`
(MLflow key `technical_task_router.benchmark_score_v2`), a bounded `[0, 1]` composite:

```text
benchmark_score/v2 = clamp(
    0.70 * success_under_budget
  + 0.15 * cost_efficiency
  + 0.10 * sparse_cell_generalization
  + 0.05 * candidate_pool_robustness,
  0.0, 1.0)
```

| Component | Scorer ref | Computation |
|---|---|---|
| Success under budget | `technical_task_router.success_under_budget/v1` | Feasible and completed rows / total rows (also the v1 guardrail). |
| Cost efficiency | `technical_task_router.cost_efficiency/v2` | Mean `1 - clamp(actual_cost_usd / max_cost_usd, 0, 1)` over successful rows. |
| Sparse-cell generalization | `technical_task_router.sparse_cell_generalization/v2` | Success-under-budget rate over the `sparse_cell` scenario slice. |
| Candidate-pool robustness | `technical_task_router.candidate_pool_robustness/v2` | Success-under-budget rate over `challenger_present`, `dominant_model_removed`, and `low_budget` slices. |

The component weights, bounds, and required scenario slices are frozen in
`src/evaluation/scorers/builtin.py`. The canonical spec is
[`schema/examples/technical_task_router_spec.v2.json`](../schema/examples/technical_task_router_spec.v2.json)
(`primary_metric.name = technical_task_router.benchmark_score/v2`,
`metric_family = "continuous"`) and the canonical row schema is
[`schema/technical_task_router_row.v2.json`](../schema/technical_task_router_row.v2.json)
(`scorer_ref` and `benchmark_spec_id` const `technical_task_router.benchmark_score/v2`).

Because the scenario slices are required, the v2 score raises if a benchmark run is missing
`sparse_cell` or candidate-pool scenario rows. The evaluate/register/promote scripts default
to `--benchmark-version v2`; registration tags `hokusai.primary_metric`,
`hokusai.metric_family=continuous`, and `hokusai.benchmark_spec_id`, which the DeltaOne
evaluator and MintRequest builder consume metric-agnostically. The on-chain DeltaVerifier
signs the canonical metric name `technical_task_router.benchmark_score/v2` and
`metric_family=continuous`.

## Row Schema

The row schema is defined in
[`schema/technical_task_router_row.v1.json`](../schema/technical_task_router_row.v1.json).

The schema version sentinel is `"technical_task_router_row/v1"`.

### Required Fields

| Field | Type | Constraints | Description |
|---|---|---|---|
| `schema_version` | string | const: `technical_task_router_row/v1` | Schema version sentinel. |
| `row_id` | string | minLength 1 | Unique row identifier. |
| `benchmark_spec_id` | string | minLength 1 | BenchmarkSpec identifier. |
| `eval_id` | string | minLength 1 | Evaluation run identifier. |
| `model_id` | string | minLength 1 | Router model being evaluated. |
| `task_descriptor` | object | opaque | Structured descriptor for the technical task. |
| `allowed_models` | string array | minItems 1 | Models the workflow is allowed to select. |
| `selected_models` | string array | none | Models selected by the predicted workflow. |
| `max_cost_usd` | number | exclusiveMinimum 0 | Per-row budget in USD. |
| `actual_cost_usd` | number | minimum 0 | Observed workflow cost in USD. |
| `completed_successfully` | boolean | none | Whether the workflow completed the task. |
| `scorer_ref` | string | const: `technical_task_router.benchmark_score/v1` | Primary scorer ref. |
| `observed_at` | string | date-time | Observation timestamp. |

### Optional Fields

| Field | Type | Description |
|---|---|---|
| `metadata` | object | Additional context that does not affect scoring. |
| `estimated_cost_usd` | number | Router-estimated workflow cost. Used only by diagnostics. |
| `actual_time_seconds` | number or null | Observed workflow duration. `null` means unknown/unavailable. Duration coverage only counts positive finite values. |
| `estimated_duration_seconds` | number or null | Router-estimated workflow duration. `null` means no positive duration evidence exists for the strategy. |
| `estimated_success_under_budget` | number | Router-estimated probability of successful completion within budget. Used only by diagnostics. |
| `routing_objective` | enum | One of `lowest_cost`, `fastest_completion`, or `highest_reliability`. Used only by objective-specific diagnostics. |
| `neighbor_provenance` | object array | Optional training-neighbor provenance for attribution-capable eval runs. Each item includes `row_id`, `submission_id`, `wallet`, `training_row_index`, `distance`, and `weight`. Persisted through `eval_results/per_row.parquet` as deterministic JSON. |

## Two-Stage Scoring

### Stage 1: Feasibility

A row is feasible when both conditions hold:

- `selected_models` is a subset of `allowed_models`
- `actual_cost_usd <= max_cost_usd`

Rows that fail feasibility receive no success credit.

### Stage 2: Outcome

A row is successful under budget when it is feasible and:

```text
completed_successfully == true
```

The primary benchmark metric counts successful rows under budget and divides by all rows in
the dataset. Empty scorer input returns `0.0`.

## Scorer Refs

| Ref | MLflow key | Computation |
|---|---|---|
| `technical_task_router.feasibility/v1` | `technical_task_router.feasibility_v1` | Feasible rows / total rows. |
| `technical_task_router.success_under_budget/v1` | `technical_task_router.success_under_budget_v1` | Feasible and completed rows / total rows. |
| `technical_task_router.benchmark_score/v1` | `technical_task_router.benchmark_score_v1` | Primary score; identical computation to success under budget. |
| `technical_task_router.invalid_selection_rate/v1` | `technical_task_router.invalid_selection_rate_v1` | Rows where `selected_models` is not a subset of `allowed_models` / total rows. Diagnostic; expected to be zero. |
| `technical_task_router.cost_mae_usd/v1` | `technical_task_router.cost_mae_usd_v1` | Mean absolute error between `estimated_cost_usd` and `actual_cost_usd`. Diagnostic. |
| `technical_task_router.duration_mae_seconds/v1` | `technical_task_router.duration_mae_seconds_v1` | Mean absolute error over rows where `actual_time_seconds > 0` and `estimated_duration_seconds` is finite. Returns `null` in the Model 30 benchmark report when no positive labels exist. Diagnostic. |
| `technical_task_router.reliability_brier_score/v1` | `technical_task_router.reliability_brier_score_v1` | Brier score for `estimated_success_under_budget` against observed success under budget. Diagnostic; lower is better. |
| `technical_task_router.lowest_cost_success_under_budget/v1` | `technical_task_router.lowest_cost_success_under_budget_v1` | Success-under-budget rate for rows with `routing_objective=lowest_cost`. Diagnostic. |
| `technical_task_router.fastest_completion_success_under_budget/v1` | `technical_task_router.fastest_completion_success_under_budget_v1` | Success-under-budget rate for rows with `routing_objective=fastest_completion`. Diagnostic. |
| `technical_task_router.highest_reliability_success_under_budget/v1` | `technical_task_router.highest_reliability_success_under_budget_v1` | Success-under-budget rate for rows with `routing_objective=highest_reliability`. Diagnostic. |

All task-router scorers consume the same full list of `technical_task_router_row/v1` rows. Unlike
sales outcome rows, task-router rows are not filtered by `scorer_ref`; objective-specific
diagnostics filter internally by `routing_objective`.

## Duration Coverage Semantics

Model 30 benchmark reports now carry an explicit `duration_coverage` block alongside scalar
metrics. It reports:

- `evaluated_rows`: scored benchmark rows after quarantine.
- `positive_label_rows`: rows with `actual_time_seconds > 0`.
- `positive_label_fraction`: `positive_label_rows / evaluated_rows`.
- `rows_with_predictions`: positive-label rows that also have a finite predicted duration.
- `prediction_fraction_within_positive_labels`: prediction coverage inside the positive-label set.
- `duration_mae_available`: whether `technical_task_router.duration_mae_seconds_v1` is meaningful.

On the June 4, 2026 regenerated cleaned holdout, `positive_label_rows = 0` and
`positive_label_fraction = 0.0`, so the baseline report records
`technical_task_router.duration_mae_seconds_v1 = null` rather than a fake zero.

`technical_task_router.benchmark_score/v2` is the promotion and reward-gating metric.
`technical_task_router.success_under_budget/v1` is retained as a logged guardrail/diagnostic
(and as the highest-weighted component of the v2 composite), not as the primary metric. The
additional v1 metrics are diagnostics for strategy routing, cost/speed estimates, reliability
calibration, and API constraint compliance. They can fail a promotion as guardrails, but they do
not drive canonical score advancement.

## EvalSpec Example (v2 canonical)

```json
{
  "primary_metric": {
    "name": "technical_task_router.benchmark_score/v2",
    "scorer_ref": "technical_task_router.benchmark_score/v2",
    "direction": "higher_is_better",
    "unit": "bounded_score",
    "threshold": 0.8
  },
  "secondary_metrics": [
    {
      "name": "technical_task_router.success_under_budget/v1",
      "scorer_ref": "technical_task_router.success_under_budget/v1",
      "direction": "higher_is_better",
      "unit": "proportion"
    }
  ],
  "guardrails": [],
  "unit_of_analysis": "technical_task",
  "metric_family": "continuous"
}
```

The full canonical spec, including every component and guardrail metric, lives in
[`schema/examples/technical_task_router_spec.v2.json`](../schema/examples/technical_task_router_spec.v2.json).
The legacy v1 spec
([`schema/examples/technical_task_router_spec.v1.json`](../schema/examples/technical_task_router_spec.v1.json))
is retained for the v1 diagnostic path only.

The API-level `task_type` value is optional and informational:

```json
{
  "task_type": "technical_task_router"
}
```

Scoring is driven by the `eval_spec` scorer refs and the row-level fields, not by
spec-level model lists or budgets.

## Attribution Provenance

When `scripts/model_30/evaluate_technical_task_router.py` is run with
`--training-manifest`, each benchmark row also carries `neighbor_provenance`.
This resolves the routed row's contributing training neighbors back to:

- `row_id`: synthesized as `<submission_id>:<row_offset_within_submission_block>`
- `submission_id`: the assembler manifest block owner
- `wallet`: contributor wallet or `null` when the manifest is under reward hold
- `training_row_index`, `distance`, `weight`: router-local neighbor metadata

Per-row artifacts store that field as deterministic JSON so
`scripts/model_30/attribute_neighbors.py` can compare baseline versus candidate
`eval_results/per_row.parquet` files and emit a shared
`schema/attribution_report.v1.json` report. Basis-point normalization uses the
Hamilton largest-remainder method with wallet ascending as the tie-break.

Retraining-based attribution (`scripts/model_30/attribute_retraining.py`) measures each
cohort's marginal lift on the canonical v2 composite by default
(`--benchmark-version v2`, `--primary-metric technical_task_router.benchmark_score_v2`), so
reward apportionment is consistent with the v2 reward-gating metric.

## Operator Rollback Notes

The v2 cutover keeps every v1 scorer registered and logged, so falling back to v1
diagnostics does not require new code — only flag overrides on the Model 30 scripts. The
on-chain `DeltaVerifier` is metric-agnostic (it signs whatever metric name/family the
MintRequest carries), so no contract change is involved either direction.

To temporarily evaluate, attribute, or register against the v1 success-under-budget metric:

- **Evaluate / compare:** run `scripts/model_30/evaluate_technical_task_router.py`
  with `--benchmark-version v1`. `primary_metric`/`primary_delta` then track
  `technical_task_router.benchmark_score_v1`; the v2 composite is omitted from the report.
- **Retraining attribution:** run `scripts/model_30/attribute_retraining.py`
  with `--benchmark-version v1` (or `--primary-metric technical_task_router.benchmark_score_v1`).
- **Registration / promotion:** run `register_technical_task_router.py` /
  `promote_technical_task_router.py` with `--benchmark-version v1`. Registration then tags
  `hokusai.primary_metric=technical_task_router.benchmark_score/v1`,
  `hokusai.metric_family=proportion`, and `hokusai.benchmark_spec_id=technical-task-router-baseline-v1`.
- **DeltaOne / MintRequest:** no override needed — the DeltaOne evaluator and mint
  orchestrator read the registered `hokusai.primary_metric` / `hokusai.metric_family` tags,
  so registering under v1 propagates the v1 metric name and `proportion` family through
  attestation and the MintRequest automatically. The synthetic dry-run builder accepts
  `--metric-family proportion` and an explicit v1 `--benchmark-spec-id` for parity.

Rolling back is a per-run choice; the default for all Model 30 scripts remains v2. Returning
to v2 requires no cleanup beyond dropping the `--benchmark-version v1` overrides.
