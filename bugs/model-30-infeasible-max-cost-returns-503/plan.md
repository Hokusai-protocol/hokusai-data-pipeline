# Implementation Plan: Model 30 infeasible `max_cost_usd` returns 503 (HOK-3127)

Linear: https://linear.app/hokusai/issue/HOK-3127

## Overview

A Model 30 predict request with `max_cost_usd=25` failed with **HTTP 503**, logged an ERROR `model_30_inference_failure`, and produced a chained traceback. This happened on 2026-09-28 at 18:10:53 UTC, request_id `41f0562f-a9de-4dad-a294-d9d6be1f4bdb`. The failure paged through three health-report signals: `customer_5xx`, `model_30_errors` and `unhandled_exceptions`.

Every candidate route cost more than the caller's budget, and the router treats that as an exception. That outcome is deterministic and caused by the request, so it is not an outage.

**Decisions (product):**
1. **Serving always answers.** Failing to return the best available route is itself a failure. When no route fits `max_cost_usd`, return **200 with the route that best matches the user's `routing_objective`**, ranked exactly as usual but with the budget filter lifted, and clearly flagged as over budget. A "most dependable" request still gets the most dependable route. The cheapest route is still returned in `tradeoffs.lowest_cost`, so the user can choose it. Because the request now succeeds, the existing debit-before-inference charge is correct. Refunding genuinely failed requests is a separate follow-up.
2. **Evaluation still enforces the budget.** An over-budget recommendation must score as a **failure** (not under budget) in the benchmark, even though serving returned it. The flag that tells the user "this is over budget" is the same signal the evaluator uses to fail the row.

## Current State

- **Router raises:** `src/models/technical_task_router.py:340-384`, in `_rank_strategies_with_diagnostics`.
  - Candidates with `estimated_cost_usd > max_cost` are hard-filtered.
  - If no `highest_reliability` route is left, it raises a bare `ValueError("No routing strategies fit max_cost_usd=...")`.
  - The diagnostics (`_strategy_diagnostics`, line 1070) are only computed on the success path.
- **Candidate list is never empty.** `_strategy_candidates` always falls back to global defaults, so the "could not be generated" branch can't be reached. The infeasible case is therefore always "every route is too expensive".
- **Adapter wraps the error:** `src/api/endpoints/model_30_adapter.py:446-458`. Any predict exception becomes `Model30InferenceError(phase=PREDICT_CALL)`.
- **Serving turns it into a 503:** `src/api/endpoints/model_serving.py:619-641`. The generic `except Exception` returns 503. `log_model_30_failure` (adapter 665-694) logs ERROR with `exc_info`, which produces the traceback, a Sentry event, and then a Linear auto-issue.
- **Filtered-pool log is invisible:** `_filter_supported_models` (adapter 364-378) logs `model_30_candidate_pool_filtered`, but the dropped IDs go only into `extra=`. The plain `logging.basicConfig` in `src/api/main.py:33` discards `extra`, so the IDs never appear in CloudWatch.
- **Empty filtered pool is silently unconstrained:** when every requested ID for a role is dropped, the role receives `[]`. The router then treats `[]` as "no filter" (`_effective_role_evidence`, 1243-1250) and can pick models the caller did not allow. This likely contributed to the incident, because a widened pool makes expensive global routes more likely.
- **No model re-registration needed:** the pyfunc pickles `TechnicalTaskRouterModel` by reference (`scripts/model_30/register_technical_task_router.py:872-881`, no `code_paths`). Methods therefore run from the API image's `/app/src/...`, and **an API image redeploy is enough**.
- **Strict response schema:** the public schema uses `extra="forbid"` (`src/api/schemas/technical_task_router_inputs.py:15-19`). `_public_diagnostics_payload` (adapter 754-761) drops any diagnostics key that isn't in `TechnicalTaskRouterDiagnostics.model_fields`, so new fields must be added to the schema.
- **Evaluation also hits this path:** `scripts/model_30/evaluate_technical_task_router.py` calls `model.predict` through `_predict_one` (line 762) and does not catch exceptions.
  - The `low_budget` scenario halves `max_cost_usd` (`LOW_BUDGET_MULTIPLIER = 0.5`, lines 76 and 578).
  - Today an infeasible row **crashes the whole evaluation run**; it is not scored as a failure.
- **The benchmark doesn't check the recommendation's cost:** `_task_router_row_is_feasible` (`src/evaluation/scorers/builtin.py:243-265`) requires two things.
  - `selected_models ⊆ allowed_models`
  - The *historical* run's `actual_cost_usd <= max_cost_usd`
  - It never looks at whether the *recommended* route fits the budget. The local copy `_row_success_under_budget` in the eval script (line 652) has the same logic.
  - So a naive serving fallback would be **scored as success** whenever the historical run fit the budget. That would inflate `success_under_budget/v1`, `cost_efficiency_v2`, `candidate_pool_robustness_v2`, and the `benchmark_score_v2` composite.
- **Adding a row field is safe:** the benchmark row schema (`_TASK_ROUTER_ROW_SCHEMA`, builtin.py:37) doesn't set `additionalProperties: false`. The scorers are also used by `src/api/services/contribution_fidelity.py`, whose rows don't carry the new field.

## Proposed Changes

1. **Router:** replace the raise with an over-budget fallback.
   - Lift the budget filter and rank all candidates by the usual `_strategy_sort_key` for each objective, so the recommendation is the best route for the user's `routing_objective`. **Budget doesn't influence the choice at all in this case.**
   - Leave the within-budget path unchanged. When any route fits, the budget stays a hard filter, as it is today.
   - Flag the result in diagnostics: `budget_exceeded: true`, `min_route_cost_usd`, and a `max_cost_exceeded` warning.
   - Mention the budget in the rationale.
2. **Public schema:** add `budget_exceeded: bool = False` and `min_route_cost_usd: float | None` to `TechnicalTaskRouterDiagnostics`. Both are additive and backward compatible.
3. **Adapter:**
   - Emit a WARNING `model_30_max_cost_exceeded` event for over-budget responses, with no traceback and no ERROR, so the fallback stays observable.
   - Make `model_30_candidate_pool_filtered` show the dropped IDs in CloudWatch by putting JSON in the message, following the `_log_validation_422` pattern in `src/api/middleware/validation_logging.py:93-95`.
   - Log `model_30_candidate_pool_emptied` when every requested ID for a role is dropped.
4. **Evaluation:** record `budget_exceeded` on every benchmark row from the router's diagnostics. The task-router scorers treat `budget_exceeded is True` as **infeasible**, so the row fails `success_under_budget` and every metric derived from it. A new diagnostic scorer, `technical_task_router.over_budget_recommendation_rate/v1`, reports how often the router had to recommend an over-budget route.
5. **Docs:** update `docs/model-30-serving.md` and the hokusai-docs Model 30 response reference.

## Implementation Phases

### Phase 1: Router over-budget fallback

In `src/models/technical_task_router.py`:

- **`_rank_strategies_with_diagnostics`:** when `feasible_routes` is empty and `max_cost is not None`:
  - `pool = candidates` and `budget_exceeded = True`.
  - Build each objective's list from `pool` sorted by the **unchanged** `_strategy_sort_key(candidate, objective)`. The only difference from the normal path is that the budget filter is not applied.
  - `tradeoffs` (built from `strategies[objective][0]` for each objective) then naturally exposes the cheapest route under `lowest_cost`.
  - If `max_cost is None` and there are no routes, keep the existing `ValueError`. It can't be reached, but leave it as a guard.
- **`_strategy_diagnostics`:**
  - Add a `budget_exceeded` kwarg and output `budget_exceeded` and `min_route_cost_usd` (the cheapest `highest_reliability` route cost, rounded to 6 places).
  - Add `"max_cost_exceeded"` to `warnings` when the budget was exceeded.
  - `feasible_candidate_count` stays 0 so it reports the truth.
- **`_predict_row`:** when the budget was exceeded, append to the rationale: `" No route fits max_cost_usd=X; returning the best <objective> route (estimated_cost_usd=Y); the cheapest route (Z) is in tradeoffs.lowest_cost."`
- Leave `_recommended_strategy` unchanged. It already returns `strategies[objective][0]`.

**Completion criteria**
- [ ] With `max_cost_usd=0.5` (below every route), `predict` returns a row whose recommended strategy is the same route the objective would pick with no budget, with `diagnostics.budget_exceeded is True` and `"max_cost_exceeded" in diagnostics.warnings`.
- [ ] Feasible budgets behave exactly as before, and existing ranking tests pass unchanged.
- [ ] `tests/unit/lineage/test_router_serializer_roundtrip.py` passes, confirming the pickled instance state is untouched.

### Phase 2: Public schema and adapter observability

- **`src/api/schemas/technical_task_router_inputs.py`:** add `budget_exceeded: bool = False` and `min_route_cost_usd: float | None = Field(default=None, ge=0)` to `TechnicalTaskRouterDiagnostics`.
- **`src/api/endpoints/model_30_adapter.py`:**
  - In `_log_model_30_routing_diagnostics` (764), also emit `logger.warning` with a JSON message for `event=model_30_max_cost_exceeded`. Include `max_cost_usd`, `min_route_cost_usd`, `candidate_count`, the recommended route and `request_id` when available.
  - In `_filter_supported_models` (364), put the JSON payload in the log message: `json.dumps({"event": "model_30_candidate_pool_filtered", "role": ..., "dropped_model_ids": [...], "accepted_count": n})`. Keep the `extra=` too.
    - Deduplicate the 3 extra calls from `summarize_candidate_pool_fidelity` (388-413) if it's simple, for example by passing a `log=False` flag, so each request logs once per role.
  - When `accepted` is empty and `dropped` is not, log a WARNING `model_30_candidate_pool_emptied` (JSON) naming the role and the dropped IDs.
    - **Behaviour stays the same** (unconstrained). Changing that is out of scope; see below.

**Completion criteria**
- [ ] The response passes `TechnicalTaskRouterPredictions` validation with the new diagnostics fields.
- [ ] `normalize_model_30_output` passes `budget_exceeded` and `min_route_cost_usd` through to the public payload.
- [ ] The over-budget path produces no ERROR log, no `exc_info` and no `model_30_inference_failure`.
- [ ] The filtered-pool and emptied-pool log messages contain the dropped IDs as text.

### Phase 3: Evaluation fails over-budget recommendations

The flag that tells a user "this route is over budget" is the same signal the evaluator uses to fail the row. Serving and evaluation therefore can't disagree.

- **`scripts/model_30/evaluate_technical_task_router.py`:**
  - In `_build_benchmark_rows` (351), add `"budget_exceeded": bool((prediction.get("diagnostics") or {}).get("budget_exceeded"))` to every row.
  - In `_row_success_under_budget` (652), return False when `row.get("budget_exceeded") is True`. This local copy feeds `per_row_metrics` and must match the registered scorer.
  - Add the over-budget count and rate to the report, broken down by `scenario` (via `_scenario_counts` or alongside it), so we can see how many `low_budget` rows needed the fallback.
- **`src/evaluation/scorers/builtin.py`:**
  - Add `"budget_exceeded": {"type": "boolean"}` to `_TASK_ROUTER_ROW_SCHEMA` properties. It stays optional, not in `required`.
  - In `_task_router_row_is_feasible` (243), return False when `row.get("budget_exceeded") is True`.
    - This one check covers `feasibility/v1`, `success_under_budget/v1`, `benchmark_score/v1`, `cost_efficiency_v2`, `sparse_cell_generalization_v2`, `candidate_pool_robustness_v2` and `benchmark_score_v2`.
    - Update the descriptions for `feasibility/v1` and `success_under_budget/v1` to say "the recommended route did not exceed max_cost_usd".
  - Register the diagnostic scorer `technical_task_router.over_budget_recommendation_rate/v1` (Aggregation.PASS_RATE, diagnostic family). It is **not** part of the v2 composite.
- **Scorer versioning:** we keep `/v1` because existing rows are unaffected.
  - Rows without the field, including historical benchmark rows and contribution-fidelity rows, default to "not exceeded" and score exactly as before.
  - Rows where it's True couldn't be produced before, because the eval crashed instead.
  - **Decided:** keep `/v1`.
- **Measure first:** before changing anything, run the current evaluation on the current holdout with the `@production` model and record whether it completes.
  - If it crashes on infeasible rows, the current baseline was produced on data that never hit this case, or the eval can't currently run. Either way, write down which.
  - After the change, the eval must complete. Scores on rows that were never over budget must be **identical** to before, and newly reachable over-budget rows must score 0.

**Completion criteria**
- [ ] A benchmark row with `budget_exceeded: true` fails `success_under_budget/v1`, `feasibility/v1` and all v2 components, even when the historical run fit the budget.
- [ ] Rows without the field (existing fixtures, contribution rows) produce the same scores as before.
- [ ] The eval completes on the full holdout. The report includes the over-budget rate per scenario.
- [ ] The eval script's `per_row_metrics` and the registered scorers agree on every row.

### Phase 4: Tests

- **`tests/unit/models/test_technical_task_router.py`:**
  - **Replace** `test_strategy_budget_raises_when_no_route_is_feasible` (line 400) with `test_strategy_budget_honors_objective_when_no_route_is_feasible`. It should assert that `highest_reliability` returns the same route as an unbudgeted request (not simply the cheapest), with `budget_exceeded`, the warning, `min_route_cost_usd`, and `tradeoffs.lowest_cost` pointing at the cheapest route (model-b, cost 1.0 in `_route_ranking_rows`). Build the fixture so the most reliable route is *not* the cheapest one, otherwise the test can't tell the two behaviours apart.
  - Add a test that a feasible budget leaves `budget_exceeded` False and `warnings` without `max_cost_exceeded`.
  - Parametrize over all three objectives: when over budget, each returns the same route as the unbudgeted ranking for that objective (`lowest_cost` → cheapest, `fastest_completion` → fastest, `highest_reliability` → most reliable).
- **`tests/unit/test_model_30_adapter.py`:**
  - Normalization keeps the new diagnostics fields.
  - `model_30_max_cost_exceeded` is emitted at WARNING (use `caplog`).
  - The filtered-pool message contains the dropped IDs.
  - An all-dropped role emits `model_30_candidate_pool_emptied`.
- **`tests/unit/test_model_serving.py`:** add an endpoint test through `client` and `_replace_registry_entry("30", model_caller=...)`. A fake model returns an over-budget payload; assert a 200 with `diagnostics.budget_exceeded` true and no ERROR records.
- **`tests/unit/test_technical_task_router_scorers.py`:**
  - A row with `budget_exceeded: true` (and a historical cost under budget) fails feasibility, success, cost efficiency and the robustness slice.
  - The same row without the field passes.
  - `over_budget_recommendation_rate/v1` is computed correctly.
  - The schema accepts the new field.
- **Evaluation script tests** (the existing `evaluate_technical_task_router` tests, or new ones):
  - With a fake model that returns `diagnostics.budget_exceeded: true` for `low_budget` rows, `_build_benchmark_rows` records the flag and `per_row_metrics` success is 0.
  - `_score_benchmark_rows` matches it.
  - An infeasible row no longer crashes the run.
- **Regression:** a real in-process round trip that `mlflow.pyfunc.save_model` / `load_model`s a small router, calls predict with an infeasible budget and gets a 200-shaped payload. This proves the fix works through the pyfunc boundary with no re-registration.

**Commands**
```bash
pytest tests/unit/models/test_technical_task_router.py -q
pytest tests/unit/test_model_30_adapter.py tests/unit/test_model_serving.py -q
pytest tests/unit/test_technical_task_router_scorers.py tests/unit/test_scorer_registry.py -q
pytest tests/unit/test_validation_logging.py tests/unit/test_model_30_latency_trace.py \
  tests/unit/lineage/test_router_serializer_roundtrip.py tests/unit/test_technical_task_router_features.py -q
pytest tests/ -q   # full unit suite before PR
```

**Evaluation before/after:** run `scripts/model_30/evaluate_technical_task_router.py` on the current holdout before and after the change. Paste both reports into the PR.
- The expected result is identical scores on rows that were never over budget.
- Over-budget rows score as failures and are counted in the new rate.
- The model is not re-registered.

### Phase 5: Docs, deploy, verify

- **`docs/model-30-serving.md` (341-411):** document the over-budget behaviour (200 plus `budget_exceeded`) and the new `model_30_max_cost_exceeded` and `model_30_candidate_pool_emptied` events. Correct the claim that "every non-2xx emits exactly one `model_30_inference_failure`" if it needs changing.
- **hokusai-docs:** update the Model 30 response reference with the two new diagnostics fields. This is an additive API change, deployed after the API.
- **Deploy:** merge through the normal `auto/integration` → `main` path. CI builds `hokusai-api` for `linux/amd64` and ECS redeploys `hokusai-api-development`. No infrastructure, database or auth-service changes.
- **Verify in development:**
  - `POST /api/v1/models/30/predict` with a valid payload and `max_cost_usd: 0.01` returns 200, `diagnostics.budget_exceeded: true`, and a rationale mentioning the budget.
  - Run a Logs Insights query on `/ecs/hokusai-api-development` for that request_id. It should show `model_30_max_cost_exceeded` at WARNING, and no `model_30_inference_failure` or `Traceback`.
  - The next daily health report shows no new `customer_5xx`, `model_30_errors` or `unhandled_exceptions` from this cause.
- Close HOK-3127 and the 2026-09-29 health-report item with links to the PR and the verification query.

## Success Criteria

**Functional**
- [ ] An infeasible `max_cost_usd` returns 200 with the best route for the requested objective (budget ignored), `diagnostics.budget_exceeded: true`, and the cheapest route in `tradeoffs.lowest_cost`.
- [ ] Feasible requests are unchanged; existing tests pass.

**Observability**
- [ ] No ERROR log, traceback or Sentry event for over-budget requests.
- [ ] Dropped candidate IDs and emptied role pools are visible in CloudWatch as text.

**Evaluation**
- [ ] Over-budget recommendations score as failures in `success_under_budget/v1` and the v2 composite. Their rate is reported per scenario.
- [ ] Rows that were never over budget score exactly as before the change.

**Technical**
- [ ] The full unit suite passes, including the pyfunc round-trip regression test.
- [ ] The response still validates against the `extra="forbid"` schema.
- [ ] Deployed through CI (amd64 image) without re-registering the model.

## Risks

- **Overrun size:** with the budget ignored, the recommendation can be well over `max_cost_usd`, for example a $60 most-dependable route against a $25 budget. `min_route_cost_usd` and `tradeoffs.lowest_cost` show how far over budget the cheapest option is.
- **Clients that ignore diagnostics** will get an over-budget route without noticing. This is mitigated by the rationale text and the `max_cost_exceeded` warning. A follow-up could have hokusai-site's Strategy Explorer show the flag.
- **Scorer semantics under `/v1`:** the stricter feasibility check only affects rows that carry `budget_exceeded: true`, and those couldn't exist before. Confirm with the before/after eval (Phase 4) and in review. We're keeping `/v1` (decided).
- **Contribution-fidelity rows** (`src/api/services/contribution_fidelity.py`) use the same scorer. They don't carry the field, so they're unaffected. A later change could add it so contributions are also judged on the recommended route's cost.
- **Remaining 503 paths:** other genuine predict-time errors still return 503 with a traceback, which is correct because those are real faults.

## Out of Scope (follow-ups to file)

- **Billing for failed requests:** debit-before-inference charges callers for real 5xx failures and schema 422s. Fixing it means either refunds or the auth-service holds flow (`/holds`, settle, release), which is cross-repo and needs the hokusai-architect agent.
- **Unconstrained fallback when a role's pool filters to empty:** decide whether to return 422 naming the unsupported IDs, or fall back to the supported catalog. This phase only makes it visible. Related: HOK-2568.
- **App-wide JSON logging:** `extra=` fields are dropped for every logger because of the plain `basicConfig`. Only the two logs above are fixed here.
- **hokusai-site UI** showing the over-budget flag.

## Model Routing

- planner: model resolution unavailable
- coder: model resolution unavailable
- reviewer: model resolution unavailable
