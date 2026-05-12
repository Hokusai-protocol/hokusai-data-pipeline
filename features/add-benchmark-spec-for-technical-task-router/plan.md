# Implementation Plan: Add BenchmarkSpec for Technical Task Router (HOK-1665)

## Objective

Add a new `technical_task_router/v1` benchmark spec family that evaluates a model's ability to produce a workflow configuration completing a structured task within an allowed model set and max-cost budget. Mirrors the existing sales custom eval pattern exactly.

## Key Design Decisions

- **Scorer canonical name**: `technical_task_router:success_within_budget` (follows `sales:*` naming convention)
- **Per-row score**: `1.0` iff `set(selected_models) ⊆ set(allowed_models) AND actual_cost_usd ≤ max_cost_usd AND completed_successfully is True`, else `0.0`
- **Aggregate**: arithmetic mean of per-row scores = `SuccessfulRunsWithinBudget / TotalRuns`
- **Dispatch**: extend custom_eval dispatch to recognize `technical_task_router:` prefixed scorer refs and route to the deterministic scorer path (analogous to `_has_direct_sales_scorer_refs`)
- **No DB migration**: BenchmarkSpec table already has the `eval_spec` JSONB column; additive only

## Phases

### Phase 1: Row Schema & Fixtures

**Files created/modified:**
- `schema/technical_task_router_row.v1.json` (new) — JSON Schema with `$id`, `$schema`, `required`, `additionalProperties: false`:
  - `schema_version`: const `"technical_task_router_row/v1"`
  - `row_id`: string
  - Sample side: `task_descriptor` (object), `allowed_models` (array[string], minItems 1, uniqueItems true), `max_cost_usd` (number, minimum 0)
  - Prediction side: `selected_models` (array[string], minItems 1, uniqueItems true), `workflow_config` (object), `actual_cost_usd` (number, minimum 0), `completed_successfully` (boolean)
- `schema/examples/technical_task_router_row.valid_success.v1.json` — success within budget
- `schema/examples/technical_task_router_row.valid_failed_completion.v1.json` — `completed_successfully: false`
- `schema/examples/technical_task_router_row.valid_over_budget.v1.json` — `actual_cost_usd > max_cost_usd`
- `schema/examples/technical_task_router_row.valid_disallowed_model.v1.json` — `selected_models` includes a model not in `allowed_models`
- `schema/examples/technical_task_router_row.invalid_negative_cost.v1.json` — negative `max_cost_usd` (fails schema)

### Phase 2: Scorer Implementation

**Files modified:**
- `src/evaluation/scorers/builtin.py` — add:
  - `_TECHNICAL_TASK_ROUTER_ROW_SCHEMA`: JSON Schema dict for input validation (mirrors `_SALES_ROW_SCHEMA`)
  - `_score_technical_task_router_row(row: dict) -> float`: per-row logic enforcing Stage 1 (allowlist + cost) and Stage 2 (completion); raises `ValueError` for missing required fields
  - `technical_task_router_success_within_budget(rows: list[dict]) -> dict[str, float]`: aggregates per-row scores into a mean; returns `{"technical_task_router:success_within_budget": mean_score}`

- `src/evaluation/scorers/metadata.py` — add `ScorerMetadata` entry for `technical_task_router:success_within_budget` with:
  - `version: "1.0.0"`, `metric_family: MetricFamily.OUTCOME`, `aggregation: Aggregation.MEAN`
  - `input_schema` referencing `technical_task_router_row/v1`
  - `output_metric_keys: ("technical_task_router:success_within_budget",)`

- `src/evaluation/scorers/registry.py` — register the new scorer callable

### Phase 3: Spec Schema Extension

**Files modified:**
- `src/api/schemas/benchmark_spec.py` — add `TechnicalTaskRouterBenchmarkSpec` Pydantic model with `kind: Literal["technical_task_router"]`, `version: Literal["v1"]`, dataset reference field (same local-path/S3/sha256 pattern as sales), `scorer_ref` validated against registry; add to discriminated union

**Files created:**
- `schema/examples/technical_task_router_spec.v1.json` — complete BenchmarkSpec fixture with `scorer_ref: "technical_task_router:success_within_budget"` and reference to a valid row fixture

### Phase 4: Dispatch Wiring

**Files modified:**
- `src/evaluation/custom_eval.py` — add:
  - `_has_direct_technical_task_router_scorer_refs(spec) -> bool`: returns True if all scorer refs have `"technical_task_router:"` prefix
  - `_load_technical_task_router_rows(...)`: loads rows from dataset file, validates `schema_version == "technical_task_router_row/v1"` (mirrors `_load_sales_outcome_rows`)
  - `_dispatch_technical_task_router_scorers(...)`: invokes scorer callable directly, returns per-row metrics + aggregate (mirrors `_dispatch_deterministic_scorers`)
  - Wire into existing dispatch routing: check `_has_direct_technical_task_router_scorer_refs` before the GenAI/sales/fallback branches

### Phase 5: Tests

**Files created:**
- `tests/unit/test_technical_task_router_scorer.py` — exhaustive per-row scorer tests:
  - Row A (all-pass) → 1.0
  - Row B (disallowed model) → 0.0
  - Row C (over budget) → 0.0
  - Row D (failed completion) → 0.0
  - Row E (boundary: actual == max) → 1.0
  - 5-row aggregate with 1 success → 0.2 ± 1e-9
  - Missing field → ValueError

- `tests/unit/test_technical_task_router_spec_fixtures.py` — validate all `valid_*` row fixtures pass schema; `invalid_*` fixtures fail

**Files modified:**
- `tests/unit/test_benchmark_spec_schemas.py` — add cases: valid router spec accepted; missing `scorer_ref` rejected; unknown kind rejected
- `tests/unit/test_scorer_registry.py` — assert `technical_task_router:success_within_budget` is registered with correct metadata; naming convention passes
- `tests/unit/test_custom_eval_dispatch.py` — assert dispatch routes `technical_task_router/v1` spec through the new scorer path

**Files created:**
- `tests/integration/test_technical_task_router_custom_eval_dispatch.py` — mirrors `tests/integration/test_sales_custom_eval_dispatch.py`: loads spec fixture + row fixtures, runs full dispatch, asserts per-row HEM artifact shape and aggregate Benchmark Score

## File Order (critical path)

1. `schema/technical_task_router_row.v1.json` + fixture files
2. `src/evaluation/scorers/builtin.py` + `metadata.py` + `registry.py`
3. `src/api/schemas/benchmark_spec.py`
4. `schema/examples/technical_task_router_spec.v1.json`
5. `src/evaluation/custom_eval.py`
6. Unit tests
7. Integration test

## Release Readiness

- **database_change_risk**: none
- **env_changes**: none
- **config_changes**: none
- **manual_steps**: none
