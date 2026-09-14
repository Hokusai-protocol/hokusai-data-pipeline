# HOK-2877 Investigation Plan: Model 30 `highest_reliability`

## 1. Bug Summary

Model 30 can assign identical success, cost, and duration estimates to different candidate routes when those routes have no exact match in the nearest-neighbor history. `highest_reliability` then has no route-specific reliability signal to rank and can fall through to confidence or cost ordering. Separately, `max_cost_usd` is only used as a score penalty and does not make an over-budget route ineligible.

The result is that a caller can request `highest_reliability` and receive the same cheap/default route as `lowest_cost`, including a route whose estimate exceeds the caller's budget.

- Linear issue: HOK-2877
- State: Backlog
- Priority: Urgent
- Project: Hokusai data pipeline
- Affected users: Model 30 callers, especially Wavemill routing flows that rely on the reliability objective
- Impact: weakens the reliability control, can select predictably worse routes, and can violate an explicit cost cap
- Severity: high because the defect affects core routing decisions, but it does not corrupt stored data

## 2. Reproduction Steps

### Verified local reproduction

1. Load `TechnicalTaskRouterModel` with two otherwise-similar historical rows:
   - route `model-a/model-a/model-a`: success `true`, score `0.95`, cost `$10`
   - route `model-b/model-b/model-b`: success `false`, score `0.20`, cost `$1`
2. Request all three workflow stages with both models allowed, objective `highest_reliability`, and `max_cost_usd=5`.
3. Inspect `model._rank_strategies(...)["highest_reliability"]`.
4. Observe that all six mixed routes with zero exact support receive the same estimates:
   - `estimated_success_under_budget=0.5225`
   - `estimated_cost_usd=5.5`
5. Observe that the exact all-`model-a` route is still selected with `estimated_cost_usd=10.0`, even though the cap is `$5`.

### Reproduction result

- Fallback estimate flattening: reproduced consistently
- Over-budget selection: reproduced consistently
- Environment: local Python 3.11.8 with the repository's installed MLflow and pandas dependencies
- External services: not required

### Regression fixture to add

Create a compact dataset fixture inside `tests/unit/models/test_technical_task_router.py` that separates:

- a cheap, lower-success feasible route;
- a more reliable feasible route;
- an even more reliable over-budget route;
- mixed routes that lack an exact historical match but have different role-level evidence.

The fixture should prove route-specific fallback estimates, budget filtering, objective separation, and deterministic tie resolution in one reusable setup.

## 3. Affected Components

### Primary model logic

- `src/models/technical_task_router.py:322`: `_rank_strategies` ranks every generated route without applying `max_cost_usd` as an eligibility filter.
- `src/models/technical_task_router.py:336`: `_strategy_candidates` builds the cross-product of up to three choices per active role.
- `src/models/technical_task_router.py:479`: `_rank_role` already computes route-specific building blocks on each `RoleChoice`, including `expected_success` and `estimated_cost_usd`.
- `src/models/technical_task_router.py:826`: `_estimate_strategy` replaces an empty exact-match set with the full neighbor set.
- `src/models/technical_task_router.py:911`: `_estimate_success_under_budget` already has a role-choice fallback branch, but the caller bypasses it by supplying non-empty aggregate neighbors.
- `src/models/technical_task_router.py:931`: `_estimate_strategy_cost` has the same unused route-choice fallback branch.
- `src/models/technical_task_router.py:978`: `_strategy_sort_key` applies objective ordering but lacks an explicit route-identity tie-breaker.

### Public response contract

- `src/api/schemas/technical_task_router_inputs.py:122`: strategy and tradeoff response models do not define a diagnostic/provenance field.
- `src/api/schemas/technical_task_router_inputs.py:154`: `TechnicalTaskRouterPredictions` forbids extra fields through the shared base model.
- `src/api/endpoints/model_30_adapter.py:696`: `_normalize_v2_router_payload` constructs a fixed public payload and therefore drops any new raw-model diagnostic unless explicitly preserved and validated.
- `src/api/endpoints/model_30_adapter.py:876`: model-ID canonicalization walks strategy payloads and should remain compatible with any additive diagnostic object.

### Packaging and rollout

- `scripts/model_30/register_technical_task_router.py:870`: the Python model is packaged into an MLflow artifact, so merging source changes alone does not update the production alias.
- `scripts/model_30/evaluate_technical_task_router.py:350`: holdout evaluation consumes the raw strategy output and is the correct pre-promotion quality gate.
- `scripts/model_30/promote_technical_task_router.py`: candidate-versus-baseline validation should be run before moving the production alias.

### Tests and documentation

- `tests/unit/models/test_technical_task_router.py`: covers strategies, successor evidence, duration, serialization, and candidate pools, but not fallback route separation or hard budget feasibility.
- `tests/unit/test_model_30_adapter.py`: covers strict response normalization and is where diagnostic preservation must be tested.
- `tests/integration/test_model_30_mlflow_serving.py`: covers live artifact normalization and can assert the additive diagnostic when a candidate artifact is available.
- `docs/model-30-serving.md` and `documentation/api-reference/model-30-routing-contract.md`: document the public response and must describe the new optional diagnostic.

No database tables, migrations, environment variables, or infrastructure changes are required.

## 4. Initial Observations

### Confirmed root causes

1. `_estimate_strategy` uses `matched if not matched.empty else neighbors`. The `else neighbors` branch gives every unsupported route the same evidence frame, so success, cost, and duration become route-independent.
2. The intended route-specific fallback already exists. Passing an empty frame to `_estimate_success_under_budget` averages the active roles' `RoleChoice.expected_success`; `_estimate_strategy_cost` likewise averages role-specific cost estimates. The current caller prevents both branches from running.
3. `max_cost_usd` reaches `_rank_role`, but `_cost_penalty` is only a soft penalty. `_rank_strategies` does not remove strategies whose estimated cost exceeds the cap.
4. `highest_reliability` does sort by descending `estimated_success_under_budget`, but identical fallback estimates make confidence and cost effective selectors. This is why the bug is estimation plus feasibility, not simply a reversed sort.
5. Current ordering is repeatable because pandas `groupby` and Python sort are stable, but the final key does not explicitly contain route identity. Determinism therefore depends on upstream iteration order.
6. The public adapter intentionally strips internal fields such as `support` and neighbor provenance. A diagnostic emitted only by the MLflow model would also disappear unless the Pydantic response and normalization code are extended.

### Relevant history

- Commit `fe52f57` introduced the strategy cross-product, aggregate fallback, objective sorting, and soft cost penalty on 2026-05-30.
- Commit `44182f8` later added successor/borrowed role evidence but retained the aggregate route fallback.
- HOK-2877 was created on 2026-08-24.
- The adjacent Wavemill issue HOK-2873 is done and defines additive provenance names `degenerate_objectives` and `candidate_spread`; HOK-2877 should use compatible semantics instead of inventing a second vocabulary.

### Existing test status

The focused model and adapter suites collected 105 tests and all 105 test bodies passed when MLflow was pointed at a local file store. The scoped command still exited nonzero because repository configuration enforced an 80% global coverage threshold while the two suites covered only 15.44% of the full repository. Use `--no-cov` for fast focused checks and the repository's full test command for the coverage gate.

## 5. Data Analysis Required

No production logs are needed to confirm the code defect. Before promotion, use the real cleaned router dataset and holdout corpus to measure:

1. The fraction of generated routes with zero exact support.
2. The number and percentage of requests where two or three objectives select the same route.
3. Candidate-spread distributions for:
   - minimum and maximum estimated cost;
   - minimum and maximum estimated success under budget;
   - feasible versus total candidate counts.
4. The fraction of historical benchmark scenarios with no feasible candidate under `max_cost_usd`.
5. Objective-specific success-under-budget and calibration metrics before and after the fix, using the existing Model 30 evaluator.
6. Selection changes by objective, especially whether `highest_reliability` moves toward higher-success routes while `lowest_cost` remains the cheapest feasible route.

Do not log task descriptions, identities, or raw historical records in the collapse warning. The route IDs, aggregate spread, candidate counts, budget, and neighbor count are sufficient.

## 6. Investigation Strategy

### Priority 1: Lock the failing behavior into tests

Add regression cases that fail on current code and assert:

- different unsupported routes receive different success and cost estimates when their role evidence differs;
- every ranked route is at or below `max_cost_usd` when a cap is provided;
- `highest_reliability` selects the feasible route with maximum `estimated_success_under_budget`;
- `lowest_cost` selects the feasible route with minimum `estimated_cost_usd`;
- equal primary and secondary metrics resolve by an explicit canonical route tuple;
- a route exactly equal to the budget remains feasible;
- a no-feasible-route input fails clearly rather than returning an over-budget route.

### Priority 2: Use route-specific fallback evidence

Keep exact route matches as the strongest evidence. When there is no exact match, estimate success and cost from the selected `RoleChoice` objects rather than the undifferentiated full neighbor frame. The smallest safe implementation is to let the existing empty-frame fallback branches run; if evaluation shows that simple role averaging is poorly calibrated, introduce an explicit shrinkage estimator that blends role evidence with the neighbor prior while retaining route-specific differences.

Any shrinkage must be deterministic, bounded, and documented. It should not reintroduce identical values by assigning the same prior weight to every route without a route-specific component.

### Priority 3: Enforce feasibility before objective ranking

Generate route estimates once, remove candidates with `estimated_cost_usd > max_cost_usd`, and then build all three objective rankings from the same feasible set. With no cap, preserve the current candidate set. With no feasible candidates, raise a specific, tested no-feasible-route error; do not silently select an over-budget route.

### Priority 4: Make ranking determinism explicit

Use these ordering rules:

- `highest_reliability`: success descending, confidence descending, cost ascending, canonical route tuple ascending.
- `lowest_cost`: cost ascending, success descending, confidence descending, canonical route tuple ascending.
- `fastest_completion`: known duration before unknown, duration ascending, cost ascending, success descending, confidence descending, canonical route tuple ascending.

Normalize `None` role IDs to an empty or sentinel string inside the canonical tuple so Python can compare every candidate consistently.

### Priority 5: Emit compatible diagnostics

Add an optional public `diagnostics` object containing:

- `degenerate_objectives`: objectives whose winning strategy has the same canonical route; include the field when two or more objectives collapse and emit a warning when all three collapse.
- `candidate_spread`: `min_cost`, `max_cost`, `min_success`, and `max_success` across the generated candidate routes, matching HOK-2873's Wavemill provenance vocabulary.
- `candidate_count` and `feasible_candidate_count` so budget-driven collapse is distinguishable from a truly singleton candidate set.

Compute degeneracy by canonical route identity, not by equal numeric estimates. Preserve the object through `_normalize_v2_router_payload`, make it optional for older artifacts, and emit a structured `model_30_objective_routes_collapsed` warning from the adapter without sensitive request content.

### Priority 6: Evaluate and roll out

1. Run the focused unit/adapter/integration tests.
2. Run Model 30 holdout evaluation for all objectives and sparse candidate-pool scenarios.
3. Compare candidate and production artifacts with the existing promotion script.
4. Deploy the additive API schema/adapter first so old and new artifacts are accepted.
5. Register and promote the corrected Model 30 artifact.
6. Complete the Wavemill companion change so `diagnostics.degenerate_objectives` and `diagnostics.candidate_spread` are retained in route provenance.

### Success criteria

- The verified reproduction no longer produces identical fallback estimates for routes with different role evidence.
- No selected or tradeoff route exceeds a provided `max_cost_usd`.
- `highest_reliability` and `lowest_cost` choose different routes when the feasible candidate set presents a real reliability/cost tradeoff.
- Repeated predictions over the same input and artifact are byte-for-byte stable for selected route, tradeoffs, and diagnostics.
- Genuine objective collapse is visible in the public response and structured logs.
- Existing callers and older MLflow artifacts remain valid because diagnostics are additive and optional.

## 7. Risk Assessment

- Routing behavior risk: high. The change intentionally alters route selection and can change spend and success outcomes.
- API compatibility risk: medium. Adding an optional response object is backward-compatible in Hokusai, but Wavemill must retain it rather than reject or discard it.
- Calibration risk: medium. Averaging role-level success/cost is route-specific but should be checked against holdout data; use shrinkage only if justified by measurements.
- Budget risk: reduced by the fix. Hard feasibility prevents selection above an explicit cap.
- Data integrity risk: low. No persistent data or schema migration is involved.
- Security/privacy risk: low if warnings contain only aggregate metrics and model IDs.
- Rollback: revert the API change or move the MLflow production alias back to the prior version. Because the response field is optional, the API can remain deployed while the model artifact is rolled back.

## 8. Timeline

- 2026-05-30: commit `fe52f57` introduced the current Model 30 v2 strategy estimator and ranking path.
- 2026-06-15: commit `44182f8` added borrowed successor evidence without changing the route-level fallback.
- 2026-08-24: HOK-2877 created and placed in Backlog.
- 2026-09-14: local code review and deterministic reproduction completed.
- Frequency: deterministic for candidate routes without an exact historical match; budget violations occur whenever the highest-ranked estimate exceeds the supplied cap.

## Proposed Change Surface

Expected modifications:

- `src/models/technical_task_router.py`
- `src/api/schemas/technical_task_router_inputs.py`
- `src/api/schemas/__init__.py` if the new nested diagnostic models are exported
- `src/api/endpoints/model_30_adapter.py`
- `tests/unit/models/test_technical_task_router.py`
- `tests/unit/test_model_30_adapter.py`
- `tests/integration/test_model_30_mlflow_serving.py`
- `docs/model-30-serving.md`
- `documentation/api-reference/model-30-routing-contract.md`

Expected validation-only use:

- `scripts/model_30/evaluate_technical_task_router.py`
- `scripts/model_30/register_technical_task_router.py`
- `scripts/model_30/promote_technical_task_router.py`

Out of scope:

- Wavemill escalation policy from HOK-2874
- changes to task classification signals from HOK-2875
- retraining-data cleanup unrelated to fallback estimation
- database, infrastructure, or UI changes
