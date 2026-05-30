# Technical Task Router Benchmark (v1)

## Objective and Scope

This document defines the Hokusai benchmark contract for evaluating a technical task
router. Each sample contains a structured task descriptor, the models the router may use,
the workflow models it selected, and the per-sample budget and observed outcome.

The benchmark score is:

```text
SuccessfulRunsWithinBudget / TotalRuns
```

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
| `actual_time_seconds` | number | Observed workflow duration. Used only by diagnostics. |
| `estimated_duration_seconds` | number | Router-estimated workflow duration. Used only by diagnostics. |
| `estimated_success_under_budget` | number | Router-estimated probability of successful completion within budget. Used only by diagnostics. |
| `routing_objective` | enum | One of `lowest_cost`, `fastest_completion`, or `highest_reliability`. Used only by objective-specific diagnostics. |

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
| `technical_task_router.duration_mae_seconds/v1` | `technical_task_router.duration_mae_seconds_v1` | Mean absolute error between `estimated_duration_seconds` and `actual_time_seconds`. Diagnostic. |
| `technical_task_router.reliability_brier_score/v1` | `technical_task_router.reliability_brier_score_v1` | Brier score for `estimated_success_under_budget` against observed success under budget. Diagnostic; lower is better. |
| `technical_task_router.lowest_cost_success_under_budget/v1` | `technical_task_router.lowest_cost_success_under_budget_v1` | Success-under-budget rate for rows with `routing_objective=lowest_cost`. Diagnostic. |
| `technical_task_router.fastest_completion_success_under_budget/v1` | `technical_task_router.fastest_completion_success_under_budget_v1` | Success-under-budget rate for rows with `routing_objective=fastest_completion`. Diagnostic. |
| `technical_task_router.highest_reliability_success_under_budget/v1` | `technical_task_router.highest_reliability_success_under_budget_v1` | Success-under-budget rate for rows with `routing_objective=highest_reliability`. Diagnostic. |

All task-router scorers consume the same full list of `technical_task_router_row/v1` rows. Unlike
sales outcome rows, task-router rows are not filtered by `scorer_ref`; objective-specific
diagnostics filter internally by `routing_objective`.

`technical_task_router.success_under_budget/v1` remains the promotion and reward-gating metric.
The additional metrics are diagnostics for strategy routing, cost/speed estimates, reliability
calibration, and API constraint compliance. They can fail a promotion as guardrails, but they do
not replace the primary benchmark score.

## EvalSpec Example

```json
{
  "primary_metric": {
    "name": "technical_task_router.benchmark_score/v1",
    "scorer_ref": "technical_task_router.benchmark_score/v1",
    "direction": "higher_is_better",
    "unit": "proportion",
    "threshold": 0.8
  },
  "secondary_metrics": [
    {
      "name": "technical_task_router.feasibility/v1",
      "scorer_ref": "technical_task_router.feasibility/v1",
      "direction": "higher_is_better",
      "unit": "proportion"
    }
  ],
  "guardrails": [],
  "unit_of_analysis": "technical_task",
  "metric_family": "proportion"
}
```

The API-level `task_type` value is optional and informational:

```json
{
  "task_type": "technical_task_router"
}
```

Scoring is driven by the `eval_spec` scorer refs and the row-level fields, not by
spec-level model lists or budgets.
