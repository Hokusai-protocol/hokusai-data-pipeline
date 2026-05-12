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