# Fix Model 30 Serving Reliability Failures - Quick Reference

**Issue ID**: HOK-1942

## Objective

Diagnose and address the ~11% 503 error rate on `POST /api/v1/models/30/predict` (Technical Task Router) by classifying MLflow inference failures into specific phases (artifact load, predict call, response normalization, timeout, or MLflow connectivity), enriching error logs with structured context (request_id, model_uri/version, phase, cold/warm path, exception class), and adding regression tests for the failing path once the root cause is confirmed.

## Key Files

- `src/api/endpoints/model_serving.py` — main inference endpoint where "Technical Task Router MLflow inference failed" is logged
- `src/api/endpoints/model_30_adapter.py` — Model 30 specific adapter wrapping MLflow load + predict
- `src/api/endpoints/latency_trace.py` — existing structured trace helper to extend with phase classification
- `src/api/middleware/validation_logging.py` — sibling pattern (HOK-1943) for structured failure logging
- `tests/unit/test_model_serving.py` and `tests/unit/test_model_30_adapter.py` — regression tests for failure classification

## Critical Constraints

1. Diagnose-then-fix: add observability + classification first; only land a behavioral fix once logs/tests confirm the dominant root cause.
2. No PII or full request payloads in logs — only request_id, model_uri/version, phase, path_type, and exception class/message.
3. Preserve existing HTTP status semantics (503 for MLflow unavailable, 500 for unexpected) — do not silently swallow failures or downgrade to 200.

## Success Criteria (High-Level)

- [ ] Every Model 30 failure log line includes request_id, model_uri (when known), version, phase, path_type (cold|warm), and exception class
- [ ] Failures are categorized into one of: `artifact_load`, `predict_call`, `response_normalization`, `timeout`, `mlflow_connectivity`
- [ ] An evidence document (or PR description) attributes the 11% 503 rate to one or more of the above categories with CloudWatch sample IDs
- [ ] New unit tests cover each classified failure phase for Model 30
- [ ] Tests and lint pass; PR created and linked to HOK-1942

## Detailed Sections

Full details available on-demand in task-packet-details.md:

- [Section 1: Complete Objective & Scope](#1-objective)
- [Section 2: Technical Context](#2-technical-context)
- [Section 3: Implementation Approach](#3-implementation-approach)
- [Section 4: Success Criteria](#4-success-criteria)
- [Section 5: Implementation Constraints](#5-implementation-constraints)
- [Section 6: Validation Steps](#6-validation-steps)
- [Section 7: Definition of Done](#7-definition-of-done)
- [Section 8: Rollback Plan](#8-rollback-plan)
- [Section 9: Release Readiness](#9-release-readiness)
- [Section 10: Proposed Labels](#10-proposed-labels)

**Implementation Note**: Start with this overview. Read detailed sections on-demand as you implement.