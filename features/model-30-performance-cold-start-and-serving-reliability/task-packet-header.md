# Model 30 Performance: Cold Start and Serving Reliability - Quick Reference

**Issue ID**: HOK-1869

## Objective

Roll up the completed cold-start (HOK-1874) and latency-budget (HOK-1875) sub-tasks into a verified, production-ready bucket by validating that Model 30 serves valid predictions within the documented latency budget on cold and warm paths, with reliability monitoring wired up. This is a parent/rollup task — both sub-tasks are Done — so the remaining work is end-to-end verification, gap analysis, and any small reliability fixes surfaced by validation.

## Key Files

- `src/api/endpoints/model_30_adapter.py`
- `src/api/endpoints/model_serving.py`
- `src/api/main.py`
- `configs/model_30_budget.yaml`
- `scripts/model_30/latency_smoke_check.py`

## Critical Constraints

1. Do not regress the latency budget enforced by `configs/model_30_budget.yaml` and `.github/workflows/model-30-latency-check.yml` (HOK-1875 already shipped).
2. Do not modify the warmup/prewarm contract from HOK-1874 without re-running the cold-vs-warm benchmark (`tests/unit/test_model_30_warmup.py`, `tests/unit/test_api_startup_prewarm.py`, `tests/unit/test_ready_endpoint_model_30.py`).
3. Docker images destined for ECS MUST be built with `--platform linux/amd64`.

## Success Criteria (High-Level)

- [ ] Cold-start and warm-path latency for Model 30 measured end-to-end and both within budget, with evidence checked into the feature folder.
- [ ] `/ready` (or equivalent) accurately reflects Model 30 warmup state; ALB does not receive traffic until warm.
- [ ] Latency smoke check (`scripts/model_30/latency_smoke_check.py`) and the latency CI workflow pass on the current branch.
- [ ] Serving reliability evidence (success rate, p50/p95/p99) gathered against a curated payload set and documented.
- [ ] Tests, lint, and PR linked to HOK-1869 with sub-task references.

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

**Implementation Note**: Both child issues (HOK-1874, HOK-1875) are already Done. This task is the rollup verification — confirm the system meets the bucket's goal end-to-end and close any residual reliability gaps surfaced by validation rather than re-implementing the sub-tasks.