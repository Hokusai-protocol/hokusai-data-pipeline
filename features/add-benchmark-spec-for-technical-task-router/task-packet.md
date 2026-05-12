# Add benchmark spec for technical task router - Quick Reference

**Issue ID**: HOK-1665

## Objective

Add a new benchmark spec type for evaluating technical task router models, where each sample consists of a structured task descriptor, allowed model set, and max cost constraint. The model must output a workflow configuration; scoring is binary (`completed_successfully == true && actual_cost_usd ≤ max_cost_usd`), with the benchmark score being the fraction of successful runs within budget. This mirrors the existing sales custom eval pattern, adding a parallel `technical_task_router` spec family with its own row schema, scorer(s), and BenchmarkSpec validation path.

## Key Files

- `src/api/schemas/benchmark_spec.py` — extend BenchmarkSpec discrimination/validation for the new spec family
- `src/evaluation/scorers/builtin.py` — add deterministic scorer(s) for budget feasibility + successful completion
- `src/evaluation/custom_eval.py` — dispatch new spec type into the custom eval pipeline
- `schema/technical_task_router_row.v1.json` (new) — row schema for benchmark samples
- `schema/examples/technical_task_router_spec.v1.json` (new) — fixture spec example

## Critical Constraints

1. Follow the established sales custom eval pattern exactly (schemas → fixtures → scorers → spec wiring → dispatch → tests); do not invent a new pattern.
2. Two-stage evaluation must be enforced deterministically: Stage 1 (model-allowlist + cost gate) collapses score to 0; Stage 2 only credits `completed_successfully == true` AND `actual_cost_usd ≤ max_cost_usd`.
3. Benchmark Score = SuccessfulRunsWithinBudget / TotalRuns; this is the only aggregate metric required for the MVP.

## Success Criteria (High-Level)

- [ ] New `technical_task_router/v1` BenchmarkSpec validates end-to-end (schemas, fixtures, service, route)
- [ ] Deterministic scorer enforces both feasibility (allowed models, cost ≤ max) and outcome (`completed_successfully`) producing a 0/1 per-row score
- [ ] Aggregate Benchmark Score = mean of per-row scores = SuccessfulRunsWithinBudget / TotalRuns
- [ ] Unit + integration tests cover happy path, model-not-allowed, cost-over-budget, and failed-completion cases
- [ ] Tests and lint pass; PR created and linked to HOK-1665

## Detailed Sections

Full details available on-demand in task-packet-details.md:

- [Section 1: Complete Objective & Scope](#1-objective)
- [Section 2: Technical Context](#2-technical-context)
- [Section 3: Implementation Approach](#3-implementation-approach)
- [Section 4: Success Criteria](#4-success-criteria)
- [Section 5: Implementation Constraints](#5-implementation-constraints)
- [Section 6: Validation Steps](#6-validation-steps)
- [Section 8: Definition of Done](#8-definition-of-done)
- [Section 9: Rollback Plan](#9-rollback-plan)
- [Section 10: Release Readiness](#10-release-readiness)
- [Section 11: Proposed Labels](#11-proposed-labels)

**Implementation Note**: Start with this overview. Read detailed sections on-demand as you implement.

---

## 1. Objective

### What
Add a new BenchmarkSpec family (`technical_task_router/v1`) that lets users define benchmarks evaluating a model's ability to produce a workflow configuration that completes a structured task within an allowed model set and a maximum USD cost budget.

### Why
Hokusai intends to launch a technical task router token whose value depends on objective, user-defined evaluation of router models. The site/UI needs a first-class benchmark spec it can render and dispatch against, mirroring the existing sales custom eval surface but with router-specific feasibility and outcome semantics (model allowlist + cost cap + binary completion). Without this spec, the router token has no on-platform evaluation pathway.

### Scope In
- New row schema: `schema/technical_task_router_row.v1.json` describing one benchmark sample (task descriptor, allowed_models, max_cost_usd) and one prediction (selected_models, workflow_config, actual_cost_usd, completed_successfully).
- New spec example: `schema/examples/technical_task_router_spec.v1.json` (and a small fixture row example or two).
- BenchmarkSpec extension in `src/api/schemas/benchmark_spec.py` to recognize and validate the new spec family (kind/version, scorer ref, dataset reference shape consistent with the sales pattern).
- Deterministic scorer(s) in `src/evaluation/scorers/builtin.py` implementing the two-stage rule (feasibility gate + outcome).
- Registration in `src/evaluation/scorers/registry.py` and metadata in `src/evaluation/scorers/metadata.py`.
- Dispatch wiring in `src/evaluation/custom_eval.py` so a `technical_task_router/v1` spec runs through the existing custom eval pipeline and emits per-row + aggregate metrics into the HEM artifact.
- Unit tests for: schema validation, scorer registry entry, scorer behaviour (allowed/disallowed, under/over budget, success/failure), spec fixture validity.
- Integration test that submits a `technical_task_router/v1` BenchmarkSpec through the same dispatch path used by sales evals and asserts the aggregate Benchmark Score.

### Scope Out
- Site/UI changes in `hokusai-site` to render or author the new spec (separate task; this packet only exposes the spec via API/schemas).
- Auth service changes — no new permissions are introduced; the benchmark route already enforces auth.
- Database/schema migrations — BenchmarkSpec storage already accommodates the existing custom eval shape; no new tables.
- DeltaOne mint gating changes for router tokens (out of scope; this spec only needs to plug into custom eval execution).
- Non-deterministic / LLM-judge scorers — Stage 2 success here is read from a boolean field on the row; no judge needed.
- Cost-prediction / cost-modelling logic — `actual_cost_usd` is supplied on the prediction row by the harness, not computed here.

---

## 2. Technical Context

### Repository
`hokusai-data-pipeline` only. No infrastructure changes; no auth-service changes; site changes are a separate follow-up.

### Key Files

- `src/api/schemas/benchmark_spec.py` — existing BenchmarkSpec union; extend with the new spec family. (Touched by HOK-1646, HOK-1593, HOK-1505.)
- `src/api/services/governance/benchmark_specs.py` — service layer that validates and stores specs (touched by HOK-1646, #172); confirm new spec passes through with no special-case needed beyond schema acceptance.
- `src/api/routes/benchmarks.py` — route layer (touched by #172); should require zero changes if the spec passes the union validation.
- `src/evaluation/custom_eval.py` — dispatch entry point used by sales evals; add a branch (or generic dispatch table extension) for `technical_task_router/v1`.
- `src/evaluation/scorers/builtin.py` — add deterministic router scorer(s).
- `src/evaluation/scorers/registry.py` — register the new scorer canonical name.
- `src/evaluation/scorers/metadata.py` — add metadata entry (e.g., per-row shape, aggregator family).
- `src/evaluation/schema.py` — only if a new row-type discriminant or HEM schema field is needed; prefer reusing existing structures.
- `schema/technical_task_router_row.v1.json` (new) — per-sample row schema (sample + prediction fields).
- `schema/examples/technical_task_router_row.v1.json` (new) — at least one valid row fixture (+ one invalid for negative tests).
- `schema/examples/technical_task_router_spec.v1.json` (new) — full BenchmarkSpec fixture wired to the new scorer.
- `tests/unit/test_benchmark_spec_schemas.py` — extend with cases for the new spec family.
- `tests/unit/test_scorer_registry.py` — assert the new scorer is registered with expected metadata.
- `tests/unit/test_custom_eval_dispatch.py` — extend to assert dispatch routes `technical_task_router/v1` through the deterministic scorer.
- `tests/unit/test_technical_task_router_scorer.py` (new) — exhaustive scorer cases (allowed/disallowed, under/over budget, success/failure, score aggregation).
- `tests/unit/test_technical_task_router_spec_fixtures.py` (new) — validate the new fixture files against schemas.
- `tests/integration/test_technical_task_router_custom_eval_dispatch.py` (new) — mirror `tests/integration/test_sales_custom_eval_dispatch.py` for the router spec.

### Relevant Subsystem Specs

> ⚠️ **Knowledge Gap**: No `.wavemill/context/` subsystem specs were surfaced for the custom-eval / BenchmarkSpec subsystem in the provided context. After implementation, consider running `wavemill context init --force` to capture the now-established "custom eval family" pattern (schema → fixtures → scorer → registry → dispatch → tests) so future spec additions can reuse it without re-deriving from sales-eval commits.

### Dependencies

- Built directly on the deterministic custom scorer registry (HOK-1503, #154) and HEM custom-eval foundation (HOK-1504/HOK-1323).
- Reuses the BenchmarkSpec validation + storage path that sales custom evals exercise (#166, HOK-1646/#169, #172).
- Reuses the dispatch path established in #156, #170, #171.
- No dependency on auth service, MLflow upgrade, or infrastructure changes.

### Architecture Notes

- The existing sales custom eval is the closest precedent (commits `cc562ce`, `93ee13d`, `298ae04`, `702073c`, `a2902f9`, `123a305`, `170`, `171`, `172`). Match its structure: a versioned row JSON Schema under `schema/`, fixture examples under `schema/examples/`, a deterministic scorer in `src/evaluation/scorers/builtin.py`, a registry entry, and a dispatch branch in `src/evaluation/custom_eval.py`.
- The two-stage rule from the issue maps cleanly onto a single deterministic per-row scorer that returns `1.0` iff `selected_models ⊆ allowed_models AND actual_cost_usd ≤ max_cost_usd AND completed_successfully == true`, else `0.0`. The aggregate Benchmark Score is then `mean(per_row_score)`, equivalent to `SuccessfulRunsWithinBudget / TotalRuns`.
- Per-row results must be persisted via the HEM per-row artifact (established in `bec2f6b` / HOK-1323) so downstream comparators/auditors see the same shape used for sales evals.
- The spec family identifier must be `technical_task_router` with `version: "v1"`, mirroring the `sales_eval_spec/v1` naming.
- All new scorer names must follow the canonical naming convention already enforced in `tests/unit/test_metric_naming.py` (see HOK-1586).

---

## 3. Implementation Approach

1. **Read the sales custom eval contract end-to-end** — `docs/sales-custom-outcome-eval-contract.md`, `docs/custom-outcome-evals-mlflow-foundation.md`, `schema/sales_outcome_row.v1.json`, and the sales fixture examples. Confirm the pattern before writing new code.
2. **Define the row schema** `schema/technical_task_router_row.v1.json` with required fields:
   - Sample side: `task_descriptor` (object, free-form but with `type: object` and a `description` field), `allowed_models` (array of non-empty strings, minItems 1, unique), `max_cost_usd` (number, ≥ 0).
   - Prediction side: `selected_models` (array of non-empty strings, minItems 1, unique), `workflow_config` (object), `actual_cost_usd` (number, ≥ 0), `completed_successfully` (boolean).
   - Top-level: `schema_version: "technical_task_router_row/v1"`, `row_id` (string).
3. **Create fixture examples** under `schema/examples/`:
   - `technical_task_router_row.valid_success.v1.json` (success within budget).
   - `technical_task_router_row.valid_failed_completion.v1.json` (`completed_successfully: false`).
   - `technical_task_router_row.valid_over_budget.v1.json` (`actual_cost_usd > max_cost_usd`).
   - `technical_task_router_row.valid_disallowed_model.v1.json` (`selected_models` contains entry not in `allowed_models`).
   - `technical_task_router_row.invalid_negative_cost.v1.json` (negative cost; must fail schema validation).
4. **Add the deterministic scorer** in `src/evaluation/scorers/builtin.py`:
   - Canonical name: `technical_task_router.success_within_budget/v1` (or the closest equivalent that passes the existing metric-naming tests — confirm by reading `tests/unit/test_metric_naming.py`).
   - Per-row logic: enforce Stage 1 (allowlist ⊇ selected_models AND `actual_cost_usd ≤ max_cost_usd`) and Stage 2 (`completed_successfully == true`); return `1.0` only when all hold, else `0.0`.
   - Aggregator: mean (reuse the existing `mean_per_n` family if applicable, otherwise mean; the spec says Benchmark Score = mean of per-row outcome).
5. **Register the scorer** in `src/evaluation/scorers/registry.py` and add a metadata entry in `src/evaluation/scorers/metadata.py` (input shape: `technical_task_router_row/v1`, output: scalar per row).
6. **Extend `src/api/schemas/benchmark_spec.py`**:
   - Add a `TechnicalTaskRouterBenchmarkSpec` variant with `kind: "technical_task_router"`, `version: "v1"`, a `dataset` reference (reuse the same local-path-or-S3-with-sha256 pattern from #169/#172), and a `scorer_ref` field naming the canonical scorer above.
   - Ensure it joins the same discriminated union the sales spec uses so route/service layers accept it without special casing.
7. **Wire dispatch in `src/evaluation/custom_eval.py`** — extend the dispatch table (where #170/#171/#172 land) so a `technical_task_router/v1` spec loads its rows, runs them through the new scorer, produces a per-row HEM artifact, and computes the aggregate.
8. **Create the BenchmarkSpec fixture** `schema/examples/technical_task_router_spec.v1.json` referencing the row fixtures or a small inline dataset, plus the scorer canonical ref.
9. **Unit tests**:
   - `tests/unit/test_benchmark_spec_schemas.py`: spec accepts valid router spec; rejects missing/invalid fields.
   - `tests/unit/test_scorer_registry.py`: assert the scorer is registered with the right metadata.
   - `tests/unit/test_technical_task_router_scorer.py` (new): exhaustive cases for the four valid fixtures plus an extra all-allowed-and-success case → exactly one row scores 1.0 and the others score 0.0; aggregate over a synthetic 5-row dataset equals `1/5`.
   - `tests/unit/test_technical_task_router_spec_fixtures.py` (new): each `valid_*` fixture parses; the `invalid_*` fixture is rejected.
   - `tests/unit/test_custom_eval_dispatch.py`: dispatch routes the router spec through the new scorer.
10. **Integration test** `tests/integration/test_technical_task_router_custom_eval_dispatch.py` — mirror `tests/integration/test_sales_custom_eval_dispatch.py`: load the new spec fixture, run the end-to-end dispatch, assert HEM per-row artifact contents and the aggregate Benchmark Score.
11. **Docs touch**: add a short `docs/technical-task-router-benchmark.md` describing the spec family, scoring rule, and row schema, linking to it from `docs/custom-outcome-evals-mlflow-foundation.md` (which already indexes the sales contract). Keep it concise — one page.
12. **Run lint + full unit + integration test suites locally before opening the PR**; ensure no unrelated files change.

---

## 4. Success Criteria

### Functional Requirements

- [ ] **[REQ-F1]** A `technical_task_router/v1` BenchmarkSpec submitted to the existing benchmark upload path is accepted (HTTP 200/201, persisted) when all required fields are present and valid; rejected with a 4xx and a field-level error otherwise.
- [ ] **[REQ-F2]** The row JSON Schema `schema/technical_task_router_row.v1.json` validates each `valid_*` fixture and rejects each `invalid_*` fixture; required fields and types match the descriptor in Section 3, step 2.
- [ ] **[REQ-F3]** The deterministic scorer returns `1.0` for a row iff `set(selected_models) ⊆ set(allowed_models) AND actual_cost_usd ≤ max_cost_usd AND completed_successfully is True`; returns `0.0` otherwise. The scorer raises a clear validation error (not a silent `0.0`) if a required field is missing from the row.
- [ ] **[REQ-F4]** Aggregate Benchmark Score over a dataset equals `SuccessfulRunsWithinBudget / TotalRuns`, i.e., the arithmetic mean of per-row scores; for a 5-row dataset with exactly 1 success the aggregate is `0.2 ± 1e-9`.
- [ ] **[REQ-F5]** The custom-eval dispatch path runs a `technical_task_router/v1` spec end-to-end and writes a per-row HEM artifact in the same structural shape sales evals produce (per-row dict keyed by `row_id`, scalar score, scorer canonical name), plus the aggregate metric.
- [ ] **[REQ-F6]** The new scorer canonical name is registered in `scorers/registry.py` with metadata in `scorers/metadata.py` and passes the existing `tests/unit/test_metric_naming.py` naming conventions.

### Non-Functional Requirements
- [ ] Per-row scoring is pure-Python and deterministic — same inputs ⇒ same outputs across runs; no network or filesystem access in the scorer itself.
- [ ] No `Any` type leakage in new typed code paths; pydantic models for the new spec follow the existing `BenchmarkSpec` typing.
- [ ] No regression in existing sales custom eval tests (all of `tests/integration/test_sales_custom_eval_dispatch.py` and related units still pass).

### Code Quality
- [ ] Follows the sales custom eval pattern (schema → fixture → scorer → registry → spec union → dispatch → tests).
- [ ] No `any`/`Any` types unless justified inline.
- [ ] No lint errors (`ruff` / project linter config).
- [ ] No unrelated changes (no formatting churn outside touched files).

---

## 5. Implementation Constraints

- **Code style**: Match the existing module structure exactly. The new scorer lives in `src/evaluation/scorers/builtin.py` alongside the sales scorers; the new spec variant lives in `src/api/schemas/benchmark_spec.py` alongside the existing variants. Use pydantic models that mirror the sales counterpart's field shape and validators.
- **Testing**:
  - Every new code path must have at least one unit test.
  - The integration test must mirror `tests/integration/test_sales_custom_eval_dispatch.py` and exercise the real dispatch entry point, not a stub.
  - Do NOT mock the scorer or registry inside scorer unit tests — call them directly with synthetic rows.
- **Security**: Validate dataset references with the same sha256/local-path/S3 rules used for sales custom evals (HOK-1646/#169, #172); do not introduce a new dataset reference format.
- **Performance**: Per-row scoring must be O(|selected_models| + |allowed_models|); use `set` membership, not nested loops. A 10k-row dataset must score in well under a second on a developer laptop.
- **Backwards compatibility**: Do not change existing `sales_eval_spec` shapes, sales scorer behaviour, or BenchmarkSpec discriminator field names. The new spec family must be additive only.
- **Naming**: Spec kind = `technical_task_router`, version = `v1`; row schema version = `technical_task_router_row/v1`. Use this exact spelling everywhere — fixture filenames, JSON Schema `$id`, pydantic `Literal` values, and scorer canonical name prefix.
- **Determinism**: No LLM, no randomness, no clock or network calls in the scorer or its registry entry.

---

## 6. Validation Steps

### Functional Requirement Validation

**[REQ-F1] BenchmarkSpec acceptance**

Validation scenario:
1. Setup: Run the API service locally (or use the FastAPI TestClient already used in `tests/unit/test_benchmark_routes.py` / `tests/unit/test_benchmark_spec_service.py`). Load `schema/examples/technical_task_router_spec.v1.json`.
2. Action: POST the spec to the benchmark upload endpoint that the sales spec uses (same route, same auth path).
3. Expected result: 200/201 with the persisted spec id; the persisted record has `kind == "technical_task_router"` and `version == "v1"`.
4. Edge cases:
   - Missing `scorer_ref` → 4xx with field error pointing at `scorer_ref`.
   - Unknown `kind: "technical_task_router_x"` → 4xx union-discriminator validation error (no scorer is dispatched).

**[REQ-F2] Row schema validation**

Validation scenario:
1. Setup: Use the project's JSON Schema validator (same path used in `tests/unit/test_sales_eval_spec_fixtures.py` and `tests/unit/test_sales_outcome_scorers_against_examples.py`).
2. Action: Validate each `schema/examples/technical_task_router_row.*.v1.json` fixture against `schema/technical_task_router_row.v1.json`.
3. Expected result: All `valid_*` fixtures pass; all `invalid_*` fixtures fail.
4. Edge cases:
   - `allowed_models: []` → fails (minItems 1).
   - `max_cost_usd: -1` → fails (minimum 0).
   - `completed_successfully: "true"` (string) → fails (type boolean).

**[REQ-F3] Deterministic scorer logic**

Validation scenario:
1. Setup: Construct rows in-test (no fixture I/O) covering all branches.
2. Action: Call the new scorer's per-row function directly on:
   - Row A: `allowed = {m1, m2}`, `selected = {m1}`, `max = 1.0`, `actual = 0.5`, `success = True` → expect `1.0`.
   - Row B: same as A but `selected = {m3}` → expect `0.0` (disallowed model).
   - Row C: same as A but `actual = 2.0` → expect `0.0` (over budget).
   - Row D: same as A but `success = False` → expect `0.0`.
   - Row E: same as A but `actual == max` → expect `1.0` (boundary, ≤).
3. Expected result: Returned scores exactly match the list above.
4. Edge cases:
   - Missing `completed_successfully` field → scorer raises a validation error (not silently 0).
   - `selected_models` empty → fails Stage 1 (`set() ⊆ allowed` is True, but spec requires minItems 1 on the row; scorer should also treat this as 0 with a clear reason or raise — match the sales pattern: rely on row-schema validation upstream and assume valid rows).

**[REQ-F4] Aggregate Benchmark Score**

Validation scenario:
1. Setup: 5 synthetic rows: 1 of "Row A" type and 4 of "Row B/C/D" types.
2. Action: Run the aggregator (mean) over per-row scores.
3. Expected result: `0.2` (within 1e-9).
4. Edge cases:
   - Empty dataset → aggregator returns `0.0` or raises a clear "no rows" error, matching whatever the existing sales aggregator does on empty input. Document the chosen behaviour in a test.
   - All-success dataset (3 rows, all Row A) → aggregate `1.0`.

**[REQ-F5] End-to-end dispatch**

Validation scenario:
1. Setup: Load `schema/examples/technical_task_router_spec.v1.json` plus a small local row dataset referenced by it.
2. Action: Invoke the custom eval dispatcher the same way `tests/integration/test_sales_custom_eval_dispatch.py` does.
3. Expected result:
   - A per-row HEM artifact is produced with a row dict keyed by `row_id`, each containing the scorer name and a 0/1 score.
   - The aggregate metric exists in the manifest with the expected value.
   - No exceptions; no warnings about unknown spec kinds.
4. Edge cases:
   - Spec references a non-existent dataset file → dispatcher raises the same "dataset not found" error sales evals raise; integration test asserts the error type.
   - Spec references an S3 dataset with mismatched sha256 → dispatcher raises the sha256 mismatch error (already exercised for sales in HOK-1646).

**[REQ-F6] Scorer registry**

Validation scenario:
1. Setup: Import the scorer registry.
2. Action: Look up the new canonical scorer name.
3. Expected result: Entry exists with non-empty metadata (input schema ref, output type scalar, deterministic flag true).
4. Edge cases:
   - Naming-convention test (`test_metric_naming.py`) passes for the new name.
   - Listing all scorers includes exactly one new entry (no duplicates from accidental double-registration).

---

### Input/Output Verification

**Valid Inputs (scorer):**
- `{allowed: [m1,m2], selected: [m1], max_cost_usd: 1.0, actual_cost_usd: 0.5, completed_successfully: true}` → `1.0`
- `{allowed: [m1,m2], selected: [m1,m2], max_cost_usd: 1.0, actual_cost_usd: 1.0, completed_successfully: true}` → `1.0` (boundary)
- `{allowed: [m1], selected: [m1], max_cost_usd: 0.0, actual_cost_usd: 0.0, completed_successfully: true}` → `1.0` (zero-cost boundary)

**Invalid Outcomes (scorer returns 0.0):**
- Selected includes a model not in `allowed_models` → `0.0`
- `actual_cost_usd > max_cost_usd` → `0.0`
- `completed_successfully: false` → `0.0`

**Invalid Inputs (row schema rejects):**
- `max_cost_usd: -1` → schema validation error: "must be ≥ 0"
- `allowed_models: []` → schema validation error: "minItems 1"
- Missing `schema_version` → schema validation error: "required field"

---

### Standard Validation Commands

```bash
# 1. Lint passes (project uses ruff per recent history)
ruff check src tests schema
# Expected: no errors

# 2. Unit tests pass (targeted)
pytest tests/unit/test_benchmark_spec_schemas.py tests/unit/test_scorer_registry.py tests/unit/test_custom_eval_dispatch.py tests/unit/test_technical_task_router_scorer.py tests/unit/test_technical_task_router_spec_fixtures.py -v
# Expected: all pass

# 3. Integration test passes
pytest tests/integration/test_technical_task_router_custom_eval_dispatch.py -v
# Expected: passes

# 4. Full suite has no regressions
pytest tests/ -q
# Expected: all pass; no failures in sales custom eval tests
```

---

### Manual Verification Checklist

- [ ] Open `schema/technical_task_router_row.v1.json` and confirm `$id`, `$schema`, and required fields match the sales row schema's conventions.
- [ ] Open `schema/examples/technical_task_router_spec.v1.json` and confirm `scorer_ref` matches the canonical name registered in `scorers/registry.py`.
- [ ] Run `grep -R "technical_task_router" src tests schema docs` and confirm every reference uses the exact same kind/version spelling.
- [ ] Confirm no changes appear in `src/evaluation/sales_metrics.py`, sales row schemas, or sales fixtures.

---

## 7. Definition of Done

- [ ] All success criteria in Section 4 are met.
- [ ] All validation scenarios in Section 6 are executed and pass with the specific outcomes stated.
- [ ] Each functional requirement has at least one concrete validation scenario.
- [ ] Edge cases (disallowed model, over-budget, failed completion, boundary cost equality, empty dataset) are documented and tested.
- [ ] No unrelated files changed; sales custom eval tests remain green.
- [ ] Commit message references HOK-1665.
- [ ] PR opened against `main` with a description that links HOK-1665, lists the new files, and summarizes the scoring rule.

---

## 8. Rollback Plan

- The change is additive (new spec family, new scorer, new fixtures, new tests). To roll back:
  - `git revert <merge-sha>` on `main`. No data migrations to undo; no database state added.
  - No feature flag is required because the spec family is only activated when a user submits a `technical_task_router/v1` spec; existing sales/other benchmarks are unaffected.
  - If a partial deploy leaves the registry referencing a missing scorer module, redeploy the previous image — registry registration is in-process only and disappears with the rollback.
- No infrastructure or DB rollback is needed.

---

## 9. Release Readiness
- **database_change_risk**: none
- **env_changes**: none
- **config_changes**: none
- **manual_steps**: none

---

## 10. Proposed Labels

**Risk Level**: `Risk: Medium`

**Justification**: New benchmark spec family, deterministic scorer, and dispatch wiring; additive only, no breaking changes, no DB migration, but it touches the BenchmarkSpec discriminated union and the custom-eval dispatch table — both load-bearing for the sales path. Medium captures the blast radius of touching shared union types without putting it in High territory (no auth/infra/migration).

---

**Files to Modify** (Auto-detected, top 5):
- `src/api/schemas/benchmark_spec.py`
- `src/evaluation/scorers/builtin.py`
- `src/evaluation/scorers/registry.py`
- `src/evaluation/custom_eval.py`
- `schema/technical_task_router_row.v1.json`

**Label**: `Files: benchmark_spec.py, builtin.py, registry.py, custom_eval.py, technical_task_router_row.v1.json`

**Purpose**: Prevents parallel tasks from modifying the same files.

---

**Architectural Layer**: `Layer: Service`

**Purpose**: Tasks from different layers can run in parallel safely. This work is in `src/evaluation/` and `src/api/schemas/` — service/business-logic layer, no UI, no DB migration, no infra.

---

**Area**: `Area: Evaluation`

**Purpose**: Avoid running 2+ tasks that touch the BenchmarkSpec/custom-eval surface simultaneously (e.g., another spec family addition or dispatch refactor).

---

**Test Coverage**: `Tests: Integration` (plus `Tests: Unit` implicitly)

**Purpose**: Avoid running multiple integration test tasks in parallel (slow and flaky).

---

**Component**: `Component: BenchmarkSpec`

**Purpose**: Avoid running 2+ tasks modifying the BenchmarkSpec discriminated union simultaneously.

---

### Label Summary

```
Suggested labels for this task:
- Risk: Medium
- Files: benchmark_spec.py, builtin.py, registry.py, custom_eval.py, technical_task_router_row.v1.json
- Layer: Service
- Area: Evaluation
- Tests: Integration
- Component: BenchmarkSpec
```

**How these labels help the autonomous workflow:**
- **Risk: Medium** — Max 2 Medium-risk tasks in parallel.
- **Files: …** — Prevents file conflicts (especially `benchmark_spec.py` and `custom_eval.py`, which other spec/dispatch tasks touch frequently).
- **Layer: Service** — Can run in parallel with UI/Infra/DB tasks.
- **Area: Evaluation** — Prevents simultaneous evaluation-surface changes.
- **Tests: Integration** — Throttles concurrent slow tests.
- **Component: BenchmarkSpec** — Prevents conflicts with other BenchmarkSpec union edits.