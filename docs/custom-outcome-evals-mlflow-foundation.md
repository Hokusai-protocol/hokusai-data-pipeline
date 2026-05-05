# Custom Outcome Evaluations — MLflow Foundation

This document describes the `eval_spec` storage layer added to `benchmark_specs` in HOK-1500.
It is a storage and API reference; downstream execution (DeltaOne, evaluation scheduler) continues
to read the legacy scalar fields (`metric_name`, `metric_direction`, `baseline_value`) until a
future task rewires those consumers to read `eval_spec` first.

## Overview

The `eval_spec` JSONB column on `benchmark_specs` provides a structured evaluation contract that
can be attached to a benchmark binding. It replaces the implicit single-metric contract expressed
by `metric_name` + `metric_direction` + `baseline_value` with an explicit, versioned schema that
supports multiple metrics, guardrails, and policy objects.

## Column Details

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| `eval_spec` | `JSONB` | `YES` | `NULL` |

Migration: `migrations/versions/014_add_eval_spec_to_benchmark_specs.py`

## EvalSpec Schema

```json
{
  "measurement_policy": { ... },
  "primary_metric": {
    "name": "accuracy",
    "direction": "higher_is_better",
    "threshold": 0.85,
    "unit": null
  },
  "secondary_metrics": [
    { "name": "f1_macro", "direction": "higher_is_better" }
  ],
  "guardrails": [
    {
      "name": "latency_p99_ms",
      "direction": "lower_is_better",
      "threshold": 500.0,
      "blocking": true
    }
  ],
  "unit_of_analysis": "row",
  "min_examples": 1000,
  "label_policy": { ... },
  "coverage_policy": { ... }
}
```

### Field Meanings

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `primary_metric` | `MetricSpec` | Yes (when eval_spec is provided) | The metric that determines promotion decisions |
| `secondary_metrics` | `list[MetricSpec]` | No | Metrics tracked for observability but not used for promotion |
| `guardrails` | `list[GuardrailSpec]` | No | Hard constraints that block promotion if breached |
| `measurement_policy` | `dict` | No | Free-form policy governing how measurements are collected (e.g., time windows, sampling) |
| `unit_of_analysis` | `str` | No | Granularity of evaluation: `"row"`, `"session"`, `"user"`, etc. |
| `min_examples` | `int` | No | Minimum number of examples required before the evaluation is considered valid (≥1) |
| `label_policy` | `dict` | No | Strategy for resolving ground-truth labels (e.g., majority vote, expert adjudication) |
| `coverage_policy` | `dict` | No | Constraints on data coverage before the result is trusted (e.g., minimum coverage fraction) |

### MetricSpec Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Metric identifier matching the evaluation output key |
| `direction` | `"higher_is_better" \| "lower_is_better"` | Yes | Optimization direction |
| `threshold` | `float \| null` | No | Target value; if set, used as the passing threshold |
| `unit` | `str \| null` | No | Optional unit label (e.g., `"ms"`, `"percent"`) |

### GuardrailSpec Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Guardrail identifier |
| `direction` | `"higher_is_better" \| "lower_is_better"` | Yes | Which direction is safe |
| `threshold` | `float` | Yes | Value that must not be breached |
| `blocking` | `bool` | No (default `true`) | Whether a breach prevents promotion |

## Legacy Synthesis

When a `benchmark_specs` row has `eval_spec = NULL`, the API synthesizes a minimal eval spec
at the response boundary. Clients reading any benchmark spec will always receive an `eval_spec`
object — never `null`.

The synthesized spec is built from existing scalar fields:

```python
{
    "primary_metric": {
        "name": row["metric_name"],
        "direction": row["metric_direction"],
        "threshold": row["baseline_value"],  # may be None
    },
    "secondary_metrics": [],
    "guardrails": [],
    "min_examples": (row["tiebreak_rules"] or {}).get("min_examples"),
}
```

This synthesis happens **only at the API response layer** (`_model_to_response` in
`src/api/routes/benchmarks.py`). The database column remains `NULL`; there is no backfill.

## Pydantic Types

Defined in `src/api/schemas/benchmark_spec.py`:

- `MetricSpec`
- `GuardrailSpec`
- `EvalSpec`

Re-exported from `src/api/schemas/__init__.py`.

## API Usage

### Create a spec with eval_spec

```json
POST /api/v1/benchmarks
{
  "model_id": "my-model",
  "provider": "hokusai",
  "dataset_reference": "s3://bucket/dataset.parquet",
  "eval_split": "test",
  "target_column": "label",
  "input_columns": ["feature_a", "feature_b"],
  "metric_name": "accuracy",
  "metric_direction": "higher_is_better",
  "eval_spec": {
    "primary_metric": {
      "name": "accuracy",
      "direction": "higher_is_better",
      "threshold": 0.90
    },
    "guardrails": [
      {
        "name": "latency_p99_ms",
        "direction": "lower_is_better",
        "threshold": 300.0
      }
    ],
    "min_examples": 500
  }
}
```

### Read a spec (legacy row)

Even rows created before HOK-1500 (with no `eval_spec` stored) will return a synthesized
`eval_spec` in `GET /api/v1/benchmarks/{spec_id}`. Consumers do not need special handling
for the `null` case.

## Metric Naming Contract (HOK-1502)

### Canonical name vs. MLflow key

Every metric has two identifiers:

| Identifier | Allowed characters | Example |
|------------|-------------------|---------|
| **Canonical Hokusai name** (`name`) | Any valid string, including colons | `workflow:success_rate_under_budget` |
| **MLflow key** (`mlflow_name`) | Letters, digits, `_`, `-`, `.`, `/`, space — **no colons** | `workflow_success_rate_under_budget` |

### Normalization rule (v1)

The only transformation is **colon → underscore**.  The single source of truth is
`src/utils/metric_naming.py`.  Any change to the replacement logic there must be reflected
in `MetricLogger` and verified against `DeltaOneEvaluator`.

### Auto-derivation

`MetricSpec.mlflow_name` and `GuardrailSpec.mlflow_name` are populated automatically by a
Pydantic `model_validator` when the field is omitted or empty.  Clients may supply an
explicit override only if it is already a valid MLflow key (colons cause `ValidationError`).

### DeltaOne three-tier lookup

When DeltaOne resolves the primary metric value from an MLflow run it tries three keys in
order, stopping at the first hit:

1. **`mlflow_name` from eval_spec** — `eval_spec.primary_metric.mlflow_name` (preferred).
2. **Normalized canonical name** — `derive_mlflow_name(canonical_name)` (colon → underscore).
3. **Literal canonical name** — the raw `metric_name` string from the spec.

All three tiers being exhausted raises a `ValueError` listing every key tried.

### Migration note

Pre-existing eval_spec rows without `mlflow_name` continue to load correctly; the Pydantic
validator computes it on read.  Pre-existing HEMs without `mlflow_name` in `primary_metric`
resolve via tier-2 or tier-3 fallback.  No database backfill is required.

## Per-Row Artifact (HOK-1323)

Every `mlflow.genai.evaluate` (and `mlflow.evaluate` when the result exposes a `result_df`)
persists a structured per-row result table as a Parquet artifact attached to the MLflow run.

### Artifact path

```
eval_results/per_row.parquet
```

### Run tag

```
hokusai.per_row_artifact_uri = "runs:/<run_id>/eval_results/per_row.parquet"
```

### HEM block

`create_hem_from_mlflow_run` reads `hokusai.per_row_artifact_uri` from the run tags and
downloads the artifact to populate the `per_row_artifact` block:

```json
{
  "uri": "runs:/<run_id>/eval_results/per_row.parquet",
  "schema": {
    "row_id": "object",
    "accuracy": "bool",
    "quality_score": "float64"
  },
  "row_count": 100,
  "sha256": "<64 hex chars>"
}
```

The field is **nullable** — runs without the tag produce `per_row_artifact: null`, and old
HEMs that pre-date this field continue to validate and load without changes.

### Column convention

| Column | Type | Notes |
|--------|------|-------|
| `row_id` | `str` | Required; synthesized from positional index if absent or if duplicates are detected |
| `<mlflow_name>` | `bool` (OUTCOME) or `float` (QUALITY / LATENCY / COST) | One column per `output_metric_keys` entry of each registered scorer ref, named by `derive_mlflow_name(key)` |
| `unit_id` | `str` | Optional; present when `RuntimeAdapterSpec.unit_of_analysis` groups rows into clusters |

For `genai:` and `judge:` prefixed scorer refs the per-row columns are preserved as-is from
`result.result_df` — no type coercion is applied because `mlflow.genai` controls the schema.

### Persistence behavior

- Written best-effort: if persisting fails for any reason (e.g. no `result_df`, empty
  DataFrame, serialization error) the evaluation still succeeds and `per_row_artifact` is
  `null`.
- The run tag is set **only after** a successful artifact upload, so a missing tag always
  means no artifact was written.
- SHA-256 stored in the HEM block is computed from the artifact bytes at read time (when
  `create_hem_from_mlflow_run` downloads the artifact to populate metadata). This allows
  integrity verification of the stored artifact.

### Out of scope

Loading the per-row artifact in DeltaOne / comparators is tracked separately (HOK-1325).

## Scope Boundaries

This task covers:

- Database column and Alembic migration
- SQLAlchemy model field
- Pydantic schema types
- Service-layer persistence and retrieval
- Route-layer mapping and legacy synthesis

**Not** covered in this task (future work):

- Rewiring DeltaOne / evaluation worker to execute against `eval_spec.primary_metric` instead
  of the scalar `metric_name` + `metric_direction` fields
- Scheduler logic for eval_spec-based evaluation runs
- Site/UI wiring
