# HOK-2877 Root-Cause Hypotheses

## Hypothesis 1: Aggregate neighbor fallback erases route-specific estimates

**Proposed Root Cause:**

When `_matching_strategy_rows` returns an empty frame, `_estimate_strategy` replaces it with the full nearest-neighbor frame. Every unsupported route is therefore scored from identical rows instead of its selected roles' evidence.

**Why This Could Cause Observed Behavior:**

`_estimate_success_under_budget`, `_estimate_strategy_cost`, and `_estimate_strategy_duration` read their values from the supplied non-empty frame before considering `RoleChoice` data. Using the same full neighbor frame makes those values identical across every non-exact route. `highest_reliability` then cannot distinguish the routes on its primary metric.

**How to Test:**

Build at least two unsupported route combinations from role choices with different expected success and cost. Assert that current code gives them identical fallback estimates. Change `_estimate_strategy` to use exact matches only and assert that the existing empty-frame branches produce different route estimates.

**Expected Outcome if Correct:**

The current implementation reproduces flat estimates; using role-specific fallback evidence separates them and causes `highest_reliability` to prefer the route with higher estimated success.

**Priority:** High
**Likelihood:** High
**Status:** Confirmed

## Hypothesis 2: `max_cost_usd` is treated as a preference rather than a constraint

**Proposed Root Cause:**

The budget is used only by `_cost_penalty` during per-role scoring. Strategy generation and objective ranking do not filter over-budget routes.

**Why This Could Cause Observed Behavior:**

A reliable route can remain first after a penalty even when its estimated route cost is above the caller's cap. The reproduction selected a `$10` route under a `$5` cap.

**How to Test:**

Generate one higher-success route above the cap and one lower-success route below it. Assert that current code can choose the over-budget route. Add a shared strategy-feasibility filter before ranking and assert that all objective winners have cost less than or equal to the cap.

**Expected Outcome if Correct:**

The over-budget route disappears from every objective ranking and the best feasible route is selected.

**Priority:** High
**Likelihood:** High
**Status:** Confirmed

## Hypothesis 3: Implicit input order determines fully tied routes

**Proposed Root Cause:**

`_strategy_sort_key` omits route identity. When all listed metrics tie, stable sorting preserves the order produced by pandas grouping and `itertools.product`.

**Why This Could Cause Observed Behavior:**

The selected cheap/default route may look deterministic in one artifact while still depending on upstream iteration behavior. Dataset or pandas changes could change the winner without any metric change.

**How to Test:**

Create candidates tied on objective metric, confidence, cost, and duration, then permute dataset row order. Compare selections before and after adding a canonical `(planner, coder, reviewer, stages)` tie-breaker.

**Expected Outcome if Correct:**

Current selection is dependent on candidate construction order in at least one permutation; the explicit route tuple produces the same winner for every permutation and repeated run.

**Priority:** Medium
**Likelihood:** Medium
**Status:** Untested

## Hypothesis 4: A model-level diagnostic will be lost at the API boundary

**Proposed Root Cause:**

`_normalize_v2_router_payload` whitelists four top-level fields and validates them through a Pydantic model configured with `extra="forbid"`. There is no public diagnostic field.

**Why This Could Cause Observed Behavior:**

Even if the MLflow model detects collapsed objective routes, the API response will not retain that information for Wavemill provenance. A diagnostic that is not in the normalized response also cannot satisfy the HOK-2873 compatibility contract.

**How to Test:**

Pass a raw v2 prediction containing `diagnostics.degenerate_objectives` and `diagnostics.candidate_spread` through `normalize_model_30_output`. Assert that current code omits it. Extend the schema and normalizer, then assert exact round-trip preservation and structured warning emission.

**Expected Outcome if Correct:**

The current adapter drops the field; the additive response model preserves it while continuing to accept older artifact output without diagnostics.

**Priority:** High
**Likelihood:** High
**Status:** Confirmed by code inspection

## Hypothesis 5: Some objective collapse is genuine rather than a bug

**Proposed Root Cause:**

The same feasible route can legitimately be cheapest, fastest, and most reliable, or the budget can reduce the feasible set to one route.

**Why This Could Cause Observed Behavior:**

After route-specific estimates and budget filtering are fixed, identical objective winners may still occur. Treating every collapse as another ranking failure would create false alarms.

**How to Test:**

Use a fixture where one route dominates all metrics and another where only one route fits the cap. Assert that all objective winners share canonical route identity, candidate spread/counts are emitted, and the adapter logs the collapse warning without changing the selected route.

**Expected Outcome if Correct:**

The router intentionally returns the same route for all objectives and provides enough diagnostic context to distinguish dominance from estimation flattening or budget restriction.

**Priority:** Medium
**Likelihood:** High
**Status:** Expected behavior to preserve
