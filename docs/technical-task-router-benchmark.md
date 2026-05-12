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

All three scorers consume the same full list of `technical_task_router_row/v1` rows. Unlike
sales outcome rows, task-router rows are not filtered per scorer.

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
