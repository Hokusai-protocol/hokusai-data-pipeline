# HOK-2877 Fix Tasks

## 1. Regression Characterization

1. [ ] Add a reusable multi-route dataset fixture to `tests/unit/models/test_technical_task_router.py`.
   a. [ ] Include at least two feasible routes with different reliability and cost.
   b. [ ] Include one higher-success route whose cost exceeds the test budget.
   c. [ ] Include route combinations with role-level evidence but no exact full-route match.
2. [ ] Add a test proving current fallback candidates flatten success and cost estimates.
3. [ ] Add a test proving current ranking can select an over-budget route.
4. [ ] Add repeated-run and permuted-row-order tests for deterministic selection.

## 2. Route-Specific Fallback Estimation

5. [ ] Update `_estimate_strategy` in `src/models/technical_task_router.py` to keep exact route evidence and use selected-role evidence when exact support is zero.
   a. [ ] Reuse the existing empty-frame branches in `_estimate_success_under_budget` and `_estimate_strategy_cost` as the initial implementation.
   b. [ ] Keep exact successor/borrowed matches working through `_role_row_matches_choice`.
   c. [ ] Update rationale text to state whether the estimate used exact-route or role-level fallback evidence.
   d. [ ] Keep fallback duration `None` unless a route-specific duration estimator is supported by evidence.
6. [ ] Evaluate the simple role-average fallback against the holdout corpus.
   a. [ ] Measure reliability Brier score and cost MAE.
   b. [ ] If calibration regresses materially, replace the average with a documented deterministic shrinkage blend of role evidence and the neighbor prior.
   c. [ ] Retain route-specific differences in every fallback variant.
7. [ ] Add tests for direct, borrowed-successor, partial-stage, and unseen-model fallback cases.

## 3. Budget Feasibility and Objective Ranking

8. [ ] Add a single strategy-feasibility filter before the per-objective sorts.
   a. [ ] Treat `estimated_cost_usd <= max_cost_usd` as feasible.
   b. [ ] Preserve all candidates when the cap is absent.
   c. [ ] Ensure the same feasible set feeds `lowest_cost`, `fastest_completion`, and `highest_reliability`.
9. [ ] Define and test a specific no-feasible-route error path that never returns an over-budget recommendation.
10. [ ] Extend `_strategy_sort_key` with canonical route identity as the final tie-breaker.
    a. [ ] `highest_reliability`: success descending, confidence descending, cost ascending, route tuple ascending.
    b. [ ] `lowest_cost`: cost ascending, success descending, confidence descending, route tuple ascending.
    c. [ ] `fastest_completion`: known duration first, duration ascending, cost ascending, success descending, confidence descending, route tuple ascending.
11. [ ] Add boundary tests for a route exactly at the budget and one minimally over budget.
12. [ ] Assert that `lowest_cost` remains the cheapest feasible route after the change.
13. [ ] Assert that `highest_reliability` selects the feasible route with the maximum `estimated_success_under_budget`.

## 4. Collapse Diagnostics and Public Contract

14. [ ] Define additive Pydantic response models in `src/api/schemas/technical_task_router_inputs.py` for Model 30 diagnostics.
    a. [ ] Add optional `degenerate_objectives` using the existing objective enum.
    b. [ ] Add `candidate_spread` with `min_cost`, `max_cost`, `min_success`, and `max_success` to match Wavemill HOK-2873.
    c. [ ] Add total and feasible candidate counts.
    d. [ ] Keep `diagnostics` optional so older MLflow artifacts remain compatible.
15. [ ] Compute candidate spread once from the generated routes and feasibility counts from the budget filter.
16. [ ] Detect degeneracy by canonical route identity after all three objective winners are selected.
    a. [ ] Record two-objective collapse in `degenerate_objectives`.
    b. [ ] Emit the all-objectives warning only when all three winners are the same route.
    c. [ ] Do not classify equal estimates on different routes as route collapse.
17. [ ] Preserve `diagnostics` through `_normalize_v2_router_payload` in `src/api/endpoints/model_30_adapter.py`.
18. [ ] Emit a structured `model_30_objective_routes_collapsed` warning from the adapter.
    a. [ ] Include canonical route IDs, objective names, candidate spread, candidate counts, budget, and neighbor count.
    b. [ ] Exclude task text, user identity, and raw training rows.
19. [ ] Add adapter tests proving diagnostics survive normalization and older raw outputs still normalize successfully.
20. [ ] Add endpoint or integration coverage proving the diagnostic appears under the public `predictions` payload.

## 5. Evaluation and Regression Safety

21. [ ] Run focused tests without the repository-wide coverage gate:

    ```bash
    env MLFLOW_TRACKING_URI=file:///private/tmp/hok-2877-mlruns \
      pytest tests/unit/models/test_technical_task_router.py \
             tests/unit/test_model_30_adapter.py \
             tests/integration/test_model_30_mlflow_serving.py \
             --no-cov -q
    ```

22. [ ] Run lint on all changed Python files:

    ```bash
    ruff check src/models/technical_task_router.py \
      src/api/schemas/technical_task_router_inputs.py \
      src/api/endpoints/model_30_adapter.py \
      tests/unit/models/test_technical_task_router.py \
      tests/unit/test_model_30_adapter.py
    ```

23. [ ] Run the existing Model 30 holdout evaluator for all objectives and candidate-pool scenarios.
    a. [ ] Compare objective-specific success-under-budget metrics with the production artifact.
    b. [ ] Compare reliability Brier score and cost MAE.
    c. [ ] Report fallback-route frequency, collapse frequency, and no-feasible-route frequency.
    d. [ ] Verify invalid-selection rate remains zero.
24. [ ] Run the full repository test command so the configured coverage gate is evaluated in its intended scope.
25. [ ] Run the live MLflow integration test against the registered candidate artifact when credentials are available; otherwise record it as an environment-dependent skip.

## 6. Documentation

26. [ ] Update `docs/model-30-serving.md`.
    a. [ ] Document strict `max_cost_usd` feasibility.
    b. [ ] Document objective-specific ordering and deterministic tie-breakers.
    c. [ ] Add the optional `diagnostics` response example.
    d. [ ] Explain genuine objective collapse and candidate-spread semantics.
27. [ ] Update `documentation/api-reference/model-30-routing-contract.md` with the additive response fields and no-feasible-route behavior.
28. [ ] Note that Wavemill must retain `degenerate_objectives` and `candidate_spread` in route provenance; do not implement Wavemill escalation or classification changes here.

## 7. Packaging, Deployment, and Monitoring

29. [ ] Deploy the additive API schema and normalization changes before promoting the new MLflow artifact.
30. [ ] Register a corrected `Technical Task Router` candidate artifact with the approved cleaned training dataset and manifest.
31. [ ] Run `scripts/model_30/promote_technical_task_router.py` against the production baseline and require existing quality gates to pass.
32. [ ] Move the production alias only after unit, holdout, promotion, and compatibility checks pass.
33. [ ] Verify the Wavemill companion release retains the new diagnostics in route provenance.
34. [ ] Monitor structured collapse warnings and objective selection distributions after promotion.
    a. [ ] Alert on any selected route whose estimated cost exceeds the request cap.
    b. [ ] Compare `highest_reliability` and `lowest_cost` route divergence rates before and after promotion.
    c. [ ] Inspect high collapse rates for calibration or candidate-pool problems without treating every collapse as an error.

## 8. Completion Criteria

35. [ ] The controlled HOK-2877 reproduction passes with route-specific fallback estimates.
36. [ ] No selected or tradeoff strategy exceeds a supplied `max_cost_usd`.
37. [ ] `highest_reliability` and `lowest_cost` separate when a feasible cost/reliability tradeoff exists.
38. [ ] Deterministic tie tests pass under repeated execution and dataset-row permutation.
39. [ ] Genuine route collapse emits the additive diagnostic and structured warning.
40. [ ] Old artifact output remains accepted by the new API adapter.
41. [ ] Candidate evaluation and promotion evidence are attached to the HOK-2877 implementation PR.
